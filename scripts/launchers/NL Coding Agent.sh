#!/usr/bin/env sh
# NL Coding Agent POSIX launcher - desktop GUI.
# Works from a source checkout (this file under scripts/launchers/) and from a
# portable payload (this file at the payload root). The packaged beta uses only the
# provisioned native runtime; a system python3 is a source-checkout developer
# fallback only (warning printed) and is never used for a packaged payload.
set -u

script_dir=$(CDPATH= cd -- "$(dirname -- "$0")" 2>/dev/null && pwd -P) || {
    echo "ERROR: cannot resolve the launcher directory." >&2
    exit 2
}
source_layout=0
case "$script_dir" in
    */scripts/launchers)
        source_layout=1
        root=$(CDPATH= cd -- "$script_dir/../.." 2>/dev/null && pwd -P) || {
            echo "ERROR: cannot resolve the repository root from scripts/launchers." >&2
            exit 2
        }
        ;;
    *)
        root="$script_dir"
        ;;
esac

if [ ! -f "$root/nl_agent.py" ]; then
    echo "ERROR: nl_agent.py not found under the resolved root: $root" >&2
    echo "Run this launcher from the repository checkout or from the beta payload root." >&2
    exit 2
fi

python_bin=""
for candidate in "$root/python/bin/python3" "$root/runtime/bin/python3"; do
    if [ -x "$candidate" ]; then
        python_bin="$candidate"
        break
    fi
done

if [ -z "$python_bin" ] && [ "$source_layout" -eq 1 ]; then
    if command -v python3 >/dev/null 2>&1; then
        python_bin=$(command -v python3)
        echo "WARNING: source-checkout developer fallback to system python3." >&2
        echo "         The packaged private beta never uses a global Python; install the" >&2
        echo "         provisioned runtime into the payload (python/bin/python3)." >&2
    fi
fi

if [ -z "$python_bin" ]; then
    echo "ERROR: no provisioned POSIX Python runtime found." >&2
    echo "Expected python/bin/python3 next to the payload root (runtime is still unmeasured/MANUAL-PENDING)." >&2
    echo "Install/build the beta payload with the bootstrapper, or run the developer launcher from a source checkout with python3." >&2
    echo "Packaged beta must not use a global Python; see docs/BOOTSTRAPPER.md and docs/PLATFORM_COMPATIBILITY_MATRIX.md." >&2
    exit 2
fi

cd "$root" || {
    echo "ERROR: cannot enter the resolved root: $root" >&2
    exit 2
}

export PYTHONPATH="$root"
export PYTHONUTF8=1
export PYTHONDONTWRITEBYTECODE=1
export PYTHONIOENCODING=utf-8
export PYTHONNOUSERSITE=1
export NO_COLOR=1
# GUI launcher: opens the desktop app only; it never starts a mission or model call.

exec "$python_bin" "$root/nl_agent.py" gui "$@"
