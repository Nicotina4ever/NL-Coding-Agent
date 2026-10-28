# SPEC-17 — Una codebase, build native e adattatori OS

Target: Windows x64 iniziale, Linux x64 per l'amico dell'utente, macOS Apple Silicon quando verificabile; varianti Intel/macOS e Linux ARM opzionali in base a domanda e prove. **Non portare DLL/Windows embeddable Python su Linux/Mac**: preparare bundle privati distinti con build/CI su piattaforme reali. Un solo repository sorgente, non copie permanenti per OS.

Adapters: OS/process runner (`cmd`/PowerShell vs POSIX shell), paths, symlink permissions, IPC, terminal/pty, subprocess cancellation, resource detection, updater, file dialogs, certificate store, icons, app data, GPU drivers, model runtime, target-specific dependencies. `nvidia-smi` se disponibile, CPU fallback, Apple Metal/MLX quando runtime compatibili; memoria unificata di Apple non equivale a VRAM libera illimitata: rilevare memoria realmente utilizzabile e benchmark.

Qt/PySide6 può dare GUI multipiattaforma, non rende automaticamente nativi CrewAI/torchaudio/WhisperX/ASR e bundle. Eseguire test nativi di startup, progetto, terminale, LLM/local provider, tool call, SQLite, shutdown/recovery, media, installer/repair. Per Linux considerare baseline glibc, Wayland/X11, Qt deps, AppImage/.deb o tarball appropriate. Per macOS considerare .app/.dmg, firma/notarizzazione/Gatekeeper, Apple Silicon, Metal support e runtime Python appropriato.

Dichiarare piattaforme supportate **solo dopo risultati test reali**. Nell'immediato non inviare la portable Windows 1,46 GB a Linux.
