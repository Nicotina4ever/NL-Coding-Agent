# SPEC-11 — Strumenti da IDE moderno (senza clonare software proprietario)

Funzionalità obiettivo: project explorer, file tabs, syntax highlighting, intelligent completion/symbol navigation, global search, semantic search, integrated terminal/PTY, git status/branches/diff/staging selettivo, testing view, problem panel, debugger, file watcher, agent chat con contesto, multi-file patch, command palette, shortcuts, optional extension architecture.

Riutilizzare standard/protocolli e componenti già disponibili: **LSP** per linguaggi e diagnostica, **DAP** per debug, **MCP** per tool esterni, Monaco o CodeMirror come editor dove conviene. VS Code extension ecosystem non è automaticamente compatibile; compatibilità opzionale va specificata e testata. Non copiare implementazioni o aspetti proprietari da Cursor/Codex.

Backend tool interfaces: enumerate/read/search/write scoped/patch, terminal exec con policy, Git diff/status/commit autorizzato, run tests, build/lint, git worktrees, dependency graph, logs. Tool outputs con formati tipizzati, timeout, stdout/stderr bounded, progress streaming, cancellazione. Terminal command safety, injection/symlink/path validation obbligatorie.

Priorità: prima editing/test reali e logging; poi viewer diff e file; poi editor + LSP; poi debugger e plugin avanzati. Verificare che non sia una GUI statica: apri, modifica, annulla, salva, lancia test, mostra risultati e persiste.
