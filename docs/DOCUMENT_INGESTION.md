# Document corpus ingestion (stage 8 D1, NL-BP-218)

Status: D1/D3 discovery + provenance + end-to-end AppServices/CLI/minimum GUI
ingestion. Reconciliation, document authority resolution, planning and execution
are NOT implemented here and remain later work.

## Scope and consent

nl_coding_agent.core.document_corpus.DocumentCorpus performs read-only document
discovery for a selected project or explicit sources. Every discovery call requires
explicit consent=True; without it ConsentRequiredError is raised. Supported sources:

- project roots (recursive documentation discovery);
- explicit files and folders;
- documentation archives (.zip/.tar/.tar.gz/.tgz, bounded);
- Git repository documentation (working tree or a pinned ref/commit);
- documentation URLs only through an injected url_reader callback (no implicit
  network; no URL reader means the URL is skipped with url-reader-missing).

Included formats: Markdown, plain text, JSON, YAML, TOML, CSV, HTML, RST/AsciiDoc,
README/AGENTS, and documentation-oriented files under specs/docs/architecture/
roadmaps/checklists. PDF/Office are ingested only through the existing optional
attachment extractors; when a library is unavailable the file is skipped with an
explicit optional-extractor-unavailable reason (fail closed, no text guess).

Ignored: .git/.hg/.svn internals, .workspace, data, python, runtime/vendor copies,
logs, caches, build/dist/bin, node_modules, virtualenvs, sqlite/databases, binaries,
images/media/model checkpoints and symlinks. Explicit symlinks are refused.

## Provenance and untrusted handling

Every DocumentRecord carries: source_kind (project/explicit/archive/git/url),
source, project-relative or archive path, URL, title, headings, sections, text,
sha256 of raw content, size, content type, git_ref, git_commit, retrieved_at,
authority_candidates, truncated, and untrusted=True (enforced in the dataclass; it
cannot be set false). Every report includes the literal untrusted marker.

Imported text is data, never instructions. The module never executes, evals or
follows content, never runs model calls, never installs/downloads anything and
never performs network I/O. Embedded prompt-injection text stays inert text.

Authority candidates (readme, agents, spec, architecture, roadmap, checklist) are
flags for later reconciliation; they are not truth claims or precedence decisions.

## Bounds and failure behavior

Configurable CorpusLimits: max_files, max_total_bytes, max_file_bytes,
max_text_chars, max_archive_files, max_archive_bytes, max_archive_member_bytes,
max_url_items, max_sections. Oversize files are skipped with an explicit reason.
Reaching a total/archive bound marks the report bounded=True and complete=False and
stops adding further content. Duplicate raw content is detected by sha256: the
first source wins, later copies are reported in duplicates with duplicate_of; the
caller must treat bounded/incomplete reports as incomplete, never as full corpus.

Archive safety: absolute paths, drive paths, .. traversal, symlink/hardlink/device
entries are refused (whole archive rejected); member count, per-member size and
total archive bytes are bounded; archives are read in memory and never extracted
to disk. Git access uses only read-only rev-parse/ls-files/ls-tree/show commands;
no push/commit/network; pinned refs read committed blob content, not the working
tree. Files are sha256-hashed before/with ingestion.

## API

    corpus = DocumentCorpus(CorpusLimits(...), extractor=None)
    report = corpus.discover(consent=True, project_roots=[root])
    report = corpus.discover(consent=True, explicit_files=[...])
    report = corpus.discover_archive(archive, consent=True)
    report = corpus.discover_git(repo, ref="HEAD", consent=True)
    report = corpus.discover_urls(urls, reader, consent=True)
    payload = report.to_dict()

extractor is injectable for tests/fake optional document extractors; production
falls back to the existing app.attachments optional extractor only.



## End-to-end usage (D3)

AppServices (consent is mandatory; URLs require a configured reader):

    services = AppServices()
    services.configure_document_ingest(url_reader=fake_reader)  # optional/tests
    report = services.document_ingest(
        project_root="K:/project", paths=["docs/spec.md"], archives=["docs.zip"],
        git_ref=None, urls=[], consent=True, limits={"max_files": 200})
    services.document_ingest_status()  # reader/extractor/limits availability

The structured result contains counts, source_kinds, per-document bounded
provenance (path/url/source_kind/sha256/size/content type/git_ref/git_commit/
authority_candidates/untrusted/truncated; raw text/sections are omitted, only a
240-character excerpt remains), authority candidates, duplicates, bounded/complete,
limits, skipped items and limitations. It never executes content, starts a model or
mission, and performs no database persistence beyond optional bounded report
metadata decided by the caller. URLs without an explicitly configured research
fetch transport return outcome=unavailable with "no implicit network"; reader
denials are surfaced as skipped URL items.

CLI (pre-model dispatch, no DB isolation surprises):

    python nl_agent.py docs ingest --project K:/project --json
    python nl_agent.py docs ingest --project . --path docs/spec.md --archive docs.zip
    python nl_agent.py docs ingest --project . --git-ref HEAD
    python nl_agent.py docs ingest --project . --url https://example.com/doc --json

Exit code 0 = completed (including bounded results with limitations), 1 = validation/
consent/unavailable/error, 2 = usage. Plain text prints counts/source kinds/authority/
limits and the literal UNTRUSTED/not-executed note. Help states docs are untrusted
and never executed. URL ingestion requires an explicitly configured research reader
in the process (the CLI never creates an implicit network transport).

GUI minimum: Projects has a non-prominent "Ingest documentation…" action (subtle
link) that opens a folder chooser, calls the injected AppServices facade and shows a
read-only structured summary dialog. No new page, no direct DB/network, no execution;
cancel and unavailable/error paths are explicit. it/en strings are included in the
catalogs.

## Remaining work (not claimed)

- reconciliation and authority/conflict handling across documents;
- document-driven planning, task generation and execution;
- persistence/citation store integration beyond the minimum CLI/GUI surface;
- optional PDF/Office acceptance on real documents and environments;
- large-corpus/performance and real-network URL acceptance.

Tests use temp fixtures, fake extractors, fake URL readers, fake AppServices and
offscreen GUI interactions only; no live network, model or interactive GUI
verification is claimed.
