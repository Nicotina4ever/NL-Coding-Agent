from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from datetime import datetime
from pathlib import Path

import yaml
from crewai import Agent, Crew, LLM, Process, Task


APP_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_MODELS = APP_ROOT / "config" / "models.yaml"
DEFAULT_PROJECT = APP_ROOT / "config" / "voicebridge.yaml"
STATE_ROOT = APP_ROOT / "state"
LOG_ROOT = APP_ROOT / "logs"


def load_yaml(path: Path) -> dict:
    with path.open("r", encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


def raw_model_name(crewai_model: str) -> str:
    return crewai_model.split("/", 1)[1] if crewai_model.startswith("ollama/") else crewai_model


def ollama_stop(crewai_model: str) -> None:
    model = raw_model_name(crewai_model)
    try:
        subprocess.run(
            ["ollama", "stop", model],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            check=False,
            timeout=30,
        )
    except Exception:
        pass


def make_llm(role_cfg: dict, base_url: str) -> LLM:
    return LLM(
        model=role_cfg["model"],
        base_url=base_url,
        temperature=role_cfg.get("temperature", 0.1),
    )


def ensure_project(project_cfg: dict) -> Path:
    root = Path(project_cfg["project"]["root"]).resolve()
    if not root.exists() or not root.is_dir():
        raise SystemExit(f"Project root non trovato: {root}")
    return root


def protected(project_cfg: dict) -> set[Path]:
    return {Path(p).resolve() for p in project_cfg["project"].get("protected_paths", [])}


def scan_repo(project_cfg: dict, max_files: int = 2500) -> dict:
    root = ensure_project(project_cfg)
    ignore = set(project_cfg["project"].get("ignore_names", []))
    protected_paths = protected(project_cfg)

    files = []
    dirs = set()
    extensions = {}
    md_files = []

    for p in root.rglob("*"):
        try:
            rp = p.resolve()
        except Exception:
            continue

        if any(part in ignore for part in p.parts):
            continue
        if rp in protected_paths:
            continue

        if p.is_dir():
            dirs.add(str(p.relative_to(root)))
            continue

        if not p.is_file():
            continue

        rel = str(p.relative_to(root))
        files.append(rel)
        ext = p.suffix.lower() or "<none>"
        extensions[ext] = extensions.get(ext, 0) + 1
        if p.suffix.lower() in {".md", ".txt"}:
            md_files.append(rel)

        if len(files) >= max_files:
            break

    top_files = []
    for name in (
        "AGENTS.md", "README.md", "README.txt", "pyproject.toml", "requirements.txt",
        "Cargo.toml", "package.json", "pnpm-lock.yaml", "package-lock.json",
        "CMakeLists.txt", "Makefile", "docker-compose.yml", "docker-compose.yaml"
    ):
        p = root / name
        if p.exists() and p.is_file():
            top_files.append(name)

    return {
        "project_root": str(root),
        "file_count_sampled": len(files),
        "extensions": dict(sorted(extensions.items(), key=lambda kv: (-kv[1], kv[0]))[:40]),
        "top_level_build_files": top_files,
        "documentation_files": md_files[:200],
        "files_sample": files[:500],
    }


def read_docs(project_cfg: dict, max_chars: int = 140_000) -> str:
    root = ensure_project(project_cfg)
    ignore = set(project_cfg["project"].get("ignore_names", []))
    protected_paths = protected(project_cfg)
    chunks = []
    used = 0

    candidates = []
    for p in root.rglob("*"):
        if any(part in ignore for part in p.parts):
            continue
        try:
            if p.resolve() in protected_paths:
                continue
        except Exception:
            continue
        if p.is_file() and p.suffix.lower() in {".md", ".txt"}:
            candidates.append(p)

    candidates.sort(key=lambda p: (
        0 if p.name.lower() in {"agents.md", "readme.md", "architecture.md", "requirements.md"} else 1,
        len(p.parts),
        str(p).lower(),
    ))

    for p in candidates:
        if used >= max_chars:
            break
        try:
            text = p.read_text(encoding="utf-8", errors="replace")
        except Exception:
            continue
        remaining = max_chars - used
        text = text[:remaining]
        rel = p.relative_to(root)
        chunk = f"\n\n===== FILE: {rel} =====\n{text}"
        chunks.append(chunk)
        used += len(chunk)

    return "".join(chunks)


def save_state(project_name: str, stage: str, content: str) -> Path:
    safe_name = "".join(c if c.isalnum() or c in "-_" else "_" for c in project_name)
    folder = STATE_ROOT / safe_name
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / f"{stage}.md"
    path.write_text(content, encoding="utf-8")
    return path


def kickoff_single(agent: Agent, task: Task) -> str:
    crew = Crew(
        agents=[agent],
        tasks=[task],
        process=Process.sequential,
        verbose=True,
    )
    result = crew.kickoff()
    return str(result)


def doctor(models_cfg: dict, project_cfg: dict) -> int:
    print("=== NL Coding Agent / DOCTOR ===")
    print(f"Python: {sys.executable}")
    print(f"Python version: {sys.version.split()[0]}")

    try:
        import crewai
        print(f"CrewAI: OK ({getattr(crewai, '__version__', 'versione non esposta')})")
    except Exception as e:
        print(f"CrewAI: ERRORE: {e}")
        return 2

    try:
        r = subprocess.run(["ollama", "list"], capture_output=True, text=True, timeout=30)
        print("Ollama: OK" if r.returncode == 0 else "Ollama: ERRORE")
        if r.stdout:
            print(r.stdout)
    except Exception as e:
        print(f"Ollama: ERRORE: {e}")
        return 3

    try:
        root = ensure_project(project_cfg)
        print(f"Progetto: OK -> {root}")
    except SystemExit as e:
        print(e)
        return 4

    required = []
    for role, cfg in models_cfg["roles"].items():
        if role == "fallback_cloud" and not cfg.get("enabled", False):
            continue
        required.append(raw_model_name(cfg["model"]))

    listed = r.stdout if 'r' in locals() else ""
    for model in required:
        status = "OK" if model in listed else "NON TROVATO"
        print(f"Modello {model}: {status}")

    print("Doctor completato.")
    return 0


def audit(models_cfg: dict, project_cfg: dict) -> int:
    project = project_cfg["project"]["name"]
    root = ensure_project(project_cfg)
    repo_map = scan_repo(project_cfg)
    docs = read_docs(project_cfg)

    architect_cfg = models_cfg["roles"]["architect"]
    base_url = models_cfg["ollama"]["base_url"]
    llm = make_llm(architect_cfg, base_url)

    agent = Agent(
        role="Senior Software Architect",
        goal=(
            "Comprendere il repository esistente e trasformare documentazione e codice "
            "in un piano di completamento realistico, senza modificare alcun file."
        ),
        backstory=(
            "Sei l'architetto principale di un team di sviluppo locale. "
            "Devi distinguere ciò che è già implementato, ciò che è incompleto e ciò "
            "che è soltanto descritto nei documenti. Non inventare risultati di test."
        ),
        llm=llm,
        verbose=True,
        allow_delegation=False,
    )

    prompt = f"""
Repository: {root}

Questa è una FASE DI AUDIT IN SOLA LETTURA.
Non proporre modifiche come se fossero già state applicate.
Non dichiarare test superati se non sono stati eseguiti.

REPO MAP:
{json.dumps(repo_map, indent=2, ensure_ascii=False)}

DOCUMENTAZIONE DISPONIBILE:
{docs}

Produci un rapporto Markdown con:
1. architettura rilevata;
2. componenti e linguaggi;
3. stato plausibile dei moduli (implementato / parziale / solo specificato / ignoto);
4. incoerenze tra documentazione e struttura reale;
5. priorità di completamento;
6. task ordinati con dipendenze;
7. quali file o directory ogni task dovrebbe interessare;
8. comandi di build/test che andrebbero verificati;
9. rischi di integrazione, concorrenza, audio real-time, networking e sicurezza;
10. task consigliato come PRIMA modifica concreta.

Sii conservativo: quando non puoi sapere qualcosa dal materiale ricevuto, scrivi "da verificare".
"""

    task = Task(
        description=prompt,
        expected_output="Un audit tecnico Markdown dettagliato e un backlog ordinato.",
        agent=agent,
    )

    try:
        result = kickoff_single(agent, task)
        path = save_state(project, "audit", result)
        print(f"\nAUDIT SALVATO: {path}")
        return 0
    finally:
        if models_cfg["ollama"].get("unload_after_stage", True):
            ollama_stop(architect_cfg["model"])


def work(models_cfg: dict, project_cfg: dict, goal: str) -> int:
    project = project_cfg["project"]["name"]
    root = ensure_project(project_cfg)
    audit_path = STATE_ROOT / "".join(c if c.isalnum() or c in "-_" else "_" for c in project) / "audit.md"

    if not audit_path.exists():
        raise SystemExit("Prima esegui AUDIT: non esiste ancora state/.../audit.md")

    audit_text = audit_path.read_text(encoding="utf-8", errors="replace")
    base_url = models_cfg["ollama"]["base_url"]

    # Fase 1: developer produce un piano d'intervento preciso.
    dev_cfg = models_cfg["roles"]["developer"]
    dev_llm = make_llm(dev_cfg, base_url)
    developer = Agent(
        role="Implementation Developer",
        goal="Preparare una modifica concreta e verificabile senza allargare inutilmente lo scope.",
        backstory=(
            "Ricevi un audit già approvato e un obiettivo specifico. "
            "Devi produrre un piano di modifica file-per-file, criteri di completamento "
            "e test. In questa versione bootstrap NON hai ancora tool di scrittura: "
            "non fingere di aver modificato file."
        ),
        llm=dev_llm,
        verbose=True,
        allow_delegation=False,
    )

    dev_task = Task(
        description=f"""
PROGETTO: {root}

AUDIT:
{audit_text}

OBIETTIVO DELL'UTENTE:
{goal}

Produci una Implementation Specification estremamente concreta:
- scope;
- file da leggere/modificare/creare;
- interfacce coinvolte;
- ordine delle modifiche;
- test automatici;
- verifiche manuali;
- rischi e rollback;
- definition of done.

IMPORTANTE: questa è ancora la versione bootstrap del Coding Agent.
Non dichiarare di avere scritto o eseguito codice: prepara la consegna per il prossimo stadio operativo.
""",
        expected_output="Implementation Specification Markdown pronta per un coder con accesso ai file.",
        agent=developer,
    )

    try:
        dev_result = kickoff_single(developer, dev_task)
        spec_path = save_state(project, "implementation_spec", dev_result)
        print(f"\nSPEC SALVATA: {spec_path}")
    finally:
        if models_cfg["ollama"].get("unload_after_stage", True):
            ollama_stop(dev_cfg["model"])

    # Fase 2: reviewer critica la specifica prima di autorizzare un futuro writer.
    rev_cfg = models_cfg["roles"]["reviewer"]
    rev_llm = make_llm(rev_cfg, base_url)
    reviewer = Agent(
        role="Code Review & Integration Gatekeeper",
        goal="Bloccare piani incompleti, conflittuali o non verificabili prima della modifica del repository.",
        backstory=(
            "Sei il gatekeeper. Controlli dipendenze, compatibilità, test e possibili regressioni. "
            "Puoi respingere la specifica e richiedere correzioni."
        ),
        llm=rev_llm,
        verbose=True,
        allow_delegation=False,
    )

    review_task = Task(
        description=f"""
OBIETTIVO:
{goal}

IMPLEMENTATION SPEC:
{dev_result}

Revisiona la specifica.
Restituisci:
- APPROVE oppure REJECT nella prima riga;
- problemi bloccanti;
- dipendenze mancanti;
- conflitti potenziali tra moduli;
- test mancanti;
- modifiche richieste;
- criteri con cui potrà essere integrata.

Non dichiarare test eseguiti.
""",
        expected_output="Verdetto APPROVE/REJECT con revisione tecnica.",
        agent=reviewer,
    )

    try:
        review_result = kickoff_single(reviewer, review_task)
        review_path = save_state(project, "review", review_result)
        print(f"\nREVIEW SALVATA: {review_path}")
        print("\nNOTA: il bootstrap si ferma qui intenzionalmente.")
        print("Il prossimo stadio aggiungerà tool di lettura/scrittura, shell, build/test e loop di debug.")
        return 0
    finally:
        if models_cfg["ollama"].get("unload_after_stage", True):
            ollama_stop(rev_cfg["model"])


def status(project_cfg: dict) -> int:
    project = project_cfg["project"]["name"]
    safe_name = "".join(c if c.isalnum() or c in "-_" else "_" for c in project)
    folder = STATE_ROOT / safe_name
    print(f"Project: {project}")
    print(f"State: {folder}")
    if not folder.exists():
        print("Nessuno stato ancora creato.")
        return 0
    for p in sorted(folder.glob("*.md")):
        stat = p.stat()
        print(f"- {p.name}: {stat.st_size} bytes, {datetime.fromtimestamp(stat.st_mtime).isoformat(timespec='seconds')}")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(prog="NL Coding Agent")
    parser.add_argument("--models", default=str(DEFAULT_MODELS))
    parser.add_argument("--project-config", default=str(DEFAULT_PROJECT))

    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("doctor")
    sub.add_parser("audit")

    w = sub.add_parser("work")
    w.add_argument("--goal", required=True)

    sub.add_parser("status")
    args = parser.parse_args()

    models_cfg = load_yaml(Path(args.models))
    project_cfg = load_yaml(Path(args.project_config))

    if args.command == "doctor":
        return doctor(models_cfg, project_cfg)
    if args.command == "audit":
        return audit(models_cfg, project_cfg)
    if args.command == "work":
        return work(models_cfg, project_cfg, args.goal)
    if args.command == "status":
        return status(project_cfg)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
