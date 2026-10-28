# Document corpus ingestion (stage 8 D1, NL-BP-218)

Status: discovery/provenance foundation only. Reconciliation, document authority
resolution, planning and execution are NOT implemented here and remain later work.

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

## Remaining work (not claimed)

- reconciliation and authority/conflict handling across documents;
- document-driven planning, task generation and execution;
- persistence/citation store integration and GUI/CLI surfaces;
- optional PDF/Office acceptance on real documents and environments;
- large-corpus/performance and real-network URL acceptance.

Tests use temp fixtures, fake extractors and fake URL readers only; no live network,
model or GUI verification is claimed.
