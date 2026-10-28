#!/usr/bin/env sh
# macOS Finder convenience wrapper: execs the real POSIX launcher next to this file.
# Keep the .command executable (mode 100755) together with the .sh launchers.
script_dir=$(CDPATH= cd -- "$(dirname -- "$0")" 2>/dev/null && pwd -P) || {
    echo "ERROR: cannot resolve the Finder wrapper location." >&2
    exit 2
}
exec "$script_dir/NL Coding Agent.sh" "$@"