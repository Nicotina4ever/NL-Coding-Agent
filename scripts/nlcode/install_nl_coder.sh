#!/usr/bin/env sh
# NL Coder VSIX installer for macOS and Linux (also usable from any POSIX shell).
# The VSIX is platform-independent; this only locates the editor CLI.
set -eu
ROOT=$(CDPATH= cd -- "$(dirname -- "$0")/../.." && pwd)
VSIX=${1:-"$ROOT/.workspace/releases/extension/NL-Coder.vsix"}
if [ ! -f "$VSIX" ]; then
    echo "NL-Coder.vsix not found: $VSIX" >&2
    echo "Build it with: npm run package:vsix (in frontend/)" >&2
    exit 2
fi
CLI=""
for candidate in code-insiders code codium cursor; do
    if command -v "$candidate" >/dev/null 2>&1; then CLI=$(command -v "$candidate"); break; fi
done
if [ -z "$CLI" ]; then
    for candidate in \
        "/Applications/Visual Studio Code - Insiders.app/Contents/Resources/app/bin/code-insiders" \
        "/Applications/Visual Studio Code.app/Contents/Resources/app/bin/code" \
        "/usr/bin/code" "/usr/local/bin/code" "/snap/bin/code" "/usr/bin/codium"; do
        if [ -x "$candidate" ]; then CLI=$candidate; break; fi
    done
fi
if [ -z "$CLI" ]; then
    echo "No VS Code-family CLI found." >&2
    echo "Install manually with: <editor> --install-extension \"$VSIX\"" >&2
    exit 2
fi
echo "Installing NL Coder with $CLI"
"$CLI" --install-extension "$VSIX" --force
echo "NL Coder installed. Reload the editor window to activate it."
