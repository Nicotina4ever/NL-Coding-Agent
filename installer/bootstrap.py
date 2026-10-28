"""Command line entry point for the NL Coding Agent bootstrapper.

Usage examples:
  python installer/bootstrap.py plan --manifest installer/platform_manifest.json
  python installer/bootstrap.py install --target C:/Users/me/NL-Coding-Agent --manifest release.json
  python installer/bootstrap.py install --offline-bundle dist/release-candidate-... --target ./app
  python installer/bootstrap.py update --target ./app --manifest release.json
  python installer/bootstrap.py repair --target ./app --manifest release.json
  python installer/bootstrap.py verify --target ./app
  python installer/bootstrap.py cache list --cache ./cache
  python installer/bootstrap.py cache verify --cache ./cache
  python installer/bootstrap.py cache prune --cache ./cache --keep-days 30 --yes

Planning is the default mode and never writes or downloads. Install/update/repair
write only the selected target and the verified cache. The tool never installs
system-wide, never needs a global Python/pip/uv/conda and never executes
downloaded code.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from installer import TOOL_NAME, TOOL_VERSION
from installer import operations
from installer.fetcher import ArtifactError, make_fetcher
from installer.platform_manifest import ManifestError, load_manifest

EXIT_OK = 0
EXIT_USAGE = 2
EXIT_VERIFICATION = 3
EXIT_FETCH = 4
EXIT_UNSAFE = 5
DEFAULT_MANIFEST = Path(__file__).resolve().parent / "platform_manifest.json"


def _print(payload: dict, as_json: bool) -> None:
    if as_json:
        print(json.dumps(payload, indent=2, ensure_ascii=False))
        return
    status = str(payload.get("status") or "")
    if "product" in payload and isinstance(payload["product"], dict):
        product = payload["product"]
        print(TOOL_NAME + " " + TOOL_VERSION + " - " + str(product.get("name"))
              + " " + str(product.get("version")))
    if status:
        print("Status: " + status)
    if "platform" in payload:
        print("Platform: " + str(payload.get("platform")))
    if "target" in payload and payload.get("target"):
        print("Target: " + str(payload["target"]))
    if payload.get("target_state"):
        print("Target state: " + str(payload["target_state"]))
    if "cache_dir" in payload:
        print("Cache: " + str(payload.get("cache_dir")))
    if "components" in payload and isinstance(payload["components"], list):
        print("Components:")
        for component in payload["components"]:
            cached = "cache-hit" if component.get("cached") else "download"
            print("  " + str(component.get("id")) + " " + str(component.get("version"))
                  + " (" + operations.human_bytes(component.get("size") or 0)
                  + ", " + cached + ")")
    if "download_bytes" in payload:
        print("Download: " + operations.human_bytes(payload.get("download_bytes") or 0))
    if "files" in payload:
        print("Files installed: " + str(payload.get("files"))
              + " (" + operations.human_bytes(payload.get("total_size") or 0) + ")")
    for warning in payload.get("warnings") or []:
        print("Warning: " + str(warning))
    if "missing" in payload and payload["missing"]:
        print("Missing files: " + str(len(payload["missing"])))
    if "modified" in payload and payload["modified"]:
        print("Modified files: " + str(len(payload["modified"])))
    if payload.get("backup"):
        print("Previous install kept at: " + str(payload["backup"]))
    if payload.get("ok") is not None:
        print("Verification: " + ("OK" if payload.get("ok") else "FAILED"))


def _common(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--manifest", default=None,
                        help="platform manifest JSON (or use --offline-bundle)")
    parser.add_argument("--offline-bundle", default=None,
                        help="directory containing manifest.json and local artifacts (no network)")
    parser.add_argument("--platform", default=None,
                        help="platform id override (default: detect host platform)")
    parser.add_argument("--cache", default=None,
                        help="shared verified cache directory (default: per-user cache)")
    parser.add_argument("--json", action="store_true", help="machine-readable output")


def _manifest_path(args: argparse.Namespace) -> Path:
    if args.offline_bundle:
        if args.manifest:
            raise ManifestError("use either --manifest or --offline-bundle, not both")
        bundle = Path(args.offline_bundle).expanduser().resolve()
        for name in ("manifest.json", "platform-manifest.json"):
            candidate = bundle / name
            if candidate.is_file():
                return candidate
        raise ManifestError("offline bundle has no manifest.json/platform-manifest.json: "
                            + str(bundle))
    if args.manifest:
        return Path(args.manifest).expanduser().resolve()
    if DEFAULT_MANIFEST.is_file():
        return DEFAULT_MANIFEST
    raise ManifestError("no manifest given and no default manifest found")


def _load(args: argparse.Namespace) -> dict:
    return load_manifest(_manifest_path(args))


def cmd_plan(args: argparse.Namespace) -> int:
    manifest = _load(args)
    plan = operations.plan_install(
        manifest,
        target=args.target,
        cache_dir=args.cache,
        platform_id=args.platform,
        offline_bundle=args.offline_bundle,
    )
    _print(plan, args.json)
    return EXIT_OK


def _fetcher_for(args: argparse.Namespace, manifest: dict):
    return make_fetcher(manifest, offline_bundle=args.offline_bundle)


def cmd_install(args: argparse.Namespace) -> int:
    manifest = _load(args)
    if not args.target:
        print("error: --target is required for install", file=sys.stderr)
        return EXIT_USAGE
    result = operations.install(
        manifest, args.target,
        cache_dir=args.cache, platform_id=args.platform,
        fetcher=_fetcher_for(args, manifest), offline_bundle=args.offline_bundle,
    )
    _print(result, args.json)
    return EXIT_OK


def cmd_update(args: argparse.Namespace) -> int:
    manifest = _load(args)
    if not args.target:
        print("error: --target is required for update", file=sys.stderr)
        return EXIT_USAGE
    result = operations.update(
        manifest, args.target,
        cache_dir=args.cache, platform_id=args.platform,
        fetcher=_fetcher_for(args, manifest), offline_bundle=args.offline_bundle,
        allow_downgrade=bool(args.allow_downgrade),
    )
    _print(result, args.json)
    return EXIT_OK


def cmd_repair(args: argparse.Namespace) -> int:
    manifest = _load(args)
    if not args.target:
        print("error: --target is required for repair", file=sys.stderr)
        return EXIT_USAGE
    result = operations.repair(
        manifest, args.target,
        cache_dir=args.cache, platform_id=args.platform,
        fetcher=_fetcher_for(args, manifest), offline_bundle=args.offline_bundle,
    )
    _print(result, args.json)
    return EXIT_OK


def cmd_verify(args: argparse.Namespace) -> int:
    if not args.target:
        print("error: --target is required for verify", file=sys.stderr)
        return EXIT_USAGE
    report = operations.verify_install(args.target)
    _print(report, args.json)
    return EXIT_OK if report["ok"] else EXIT_VERIFICATION


def cmd_cache(args: argparse.Namespace) -> int:
    cache = args.cache or str(operations.default_cache_dir())
    action = str(getattr(args, "cache_action", "") or "list")
    if action == "list":
        payload = operations.cache_list(cache)
        _print(payload, args.json)
        return EXIT_OK
    if action == "verify":
        payload = operations.cache_verify(cache)
        _print(payload, args.json)
        return EXIT_OK if payload["ok"] else EXIT_VERIFICATION
    if action == "prune":
        payload = operations.cache_prune(cache, keep_days=args.keep_days, yes=bool(args.yes))
        _print(payload, args.json)
        return EXIT_OK if payload["status"] == "pruned" else EXIT_USAGE
    if action == "clear":
        payload = operations.cache_clear(cache, yes=bool(args.yes))
        _print(payload, args.json)
        return EXIT_OK if payload["status"] == "cleared" else EXIT_USAGE
    print("error: unknown cache action: " + action, file=sys.stderr)
    return EXIT_USAGE


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="nl-coding-agent-installer",
        description="Per-user, manifest-driven NL Coding Agent bootstrapper (plan is the default mode).",
    )
    parser.add_argument("--version", action="version",
                        version=TOOL_NAME + " " + TOOL_VERSION)
    sub = parser.add_subparsers(dest="command")

    plan_parser = sub.add_parser("plan", help="show the install/update plan (never writes or downloads)")
    _common(plan_parser)
    plan_parser.add_argument("--target", default=None, help="candidate install target (optional)")

    install_parser = sub.add_parser("install", help="install into a new/empty user-selected target")
    _common(install_parser)
    install_parser.add_argument("--target", required=True, help="user-selected install directory")

    update_parser = sub.add_parser("update", help="update an existing bootstrapper installation")
    _common(update_parser)
    update_parser.add_argument("--target", required=True)
    update_parser.add_argument("--allow-downgrade", action="store_true")

    repair_parser = sub.add_parser("repair", help="verify and reinstall damaged managed files")
    _common(repair_parser)
    repair_parser.add_argument("--target", required=True)

    verify_parser = sub.add_parser("verify", help="verify installed files against install.json")
    verify_parser.add_argument("--target", required=True)
    verify_parser.add_argument("--json", action="store_true")

    cache_parser = sub.add_parser("cache", help="shared verified cache management")
    cache_sub = cache_parser.add_subparsers(dest="cache_action", required=True)
    list_parser = cache_sub.add_parser("list", help="list cached artifacts")
    list_parser.add_argument("--cache", default=None)
    list_parser.add_argument("--json", action="store_true")
    verify_cache_parser = cache_sub.add_parser("verify", help="verify cached artifact hashes")
    verify_cache_parser.add_argument("--cache", default=None)
    verify_cache_parser.add_argument("--json", action="store_true")
    prune_parser = cache_sub.add_parser("prune", help="remove old cache artifacts (requires --yes)")
    prune_parser.add_argument("--cache", default=None)
    prune_parser.add_argument("--keep-days", type=float, default=30.0)
    prune_parser.add_argument("--yes", action="store_true")
    prune_parser.add_argument("--json", action="store_true")
    clear_parser = cache_sub.add_parser("clear", help="remove all cached artifacts (requires --yes)")
    clear_parser.add_argument("--cache", default=None)
    clear_parser.add_argument("--yes", action="store_true")
    clear_parser.add_argument("--json", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.command is None:
        args = parser.parse_args(["plan"])
    handlers = {
        "plan": cmd_plan,
        "install": cmd_install,
        "update": cmd_update,
        "repair": cmd_repair,
        "verify": cmd_verify,
        "cache": cmd_cache,
    }
    handler = handlers.get(str(args.command))
    if handler is None:
        parser.print_help()
        return EXIT_USAGE
    try:
        return handler(args)
    except ManifestError as exc:
        print("error: " + str(exc), file=sys.stderr)
        return EXIT_USAGE
    except (operations.TargetError, operations.NotInstalledError,
            operations.InstallError) as exc:
        print("error: " + str(exc), file=sys.stderr)
        return EXIT_USAGE
    except ArtifactError as exc:
        print("artifact verification/download error: " + str(exc), file=sys.stderr)
        return EXIT_FETCH
    except OSError as exc:
        print("error: " + str(exc), file=sys.stderr)
        return EXIT_USAGE


if __name__ == "__main__":
    raise SystemExit(main())
