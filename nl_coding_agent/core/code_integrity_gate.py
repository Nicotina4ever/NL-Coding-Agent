"""Minimal CodeIntegrityGate — stub / placeholder / weakened-test detection."""
from __future__ import annotations
import re


def _line_count(text: str) -> int:
    return len(text.splitlines())


def detect_stub(content: str, baseline: str | None = None) -> bool:
    # Strong signal: function/class body is only pass with minimal structure
    # Compare to baseline: if real code existed and is now stub -> true
    stripped = content.strip()
    if not stripped:
        return False
    # If only a stub class/method remains and length dropped >70% vs baseline
    if baseline is not None:
        if len(stripped) < 0.3 * len(baseline.strip()):
            return True
    # Direct stub patterns
    # A file that is mostly pass with very few lines
    pass_lines = stripped.splitlines()
    if len(pass_lines) <= 10:
        if all("pass" in ln or ln.startswith("#") or ln.startswith("\"") or ln.startswith("'") or ln.startswith("def ") or ln.startswith("class ") or ln.startswith("import ") or ln.startswith("from ") for ln in pass_lines):
            # If at least one function/class declaration and rest pass/import
            if any("def " in ln or "class " in ln for ln in pass_lines):
                # Check if any real logic line (not pass/import/def/class/comment/string)
                real = [ln for ln in pass_lines if ln.strip() and not ln.strip().startswith("#") and "pass" not in ln and not ln.strip().startswith("\"") and not ln.strip().startswith("'") and "def " not in ln and "class " not in ln and "import " not in ln and "from " not in ln]
                if len(real) == 0:
                    return True
    return False


def detect_weak_test(baseline: str, current: str) -> bool:
    baseline_asserts = baseline.count("assert ") + baseline.count("self.assert")
    current_asserts = current.count("assert ") + current.count("self.assert")
    if current_asserts < baseline_asserts * 0.5 and baseline_asserts > 0:
        return True
    # If original meaningful assertions removed and only import/unittest remains
    if current_asserts <= 1 and baseline_asserts > 2:
        if "assert True" in current or "assert False" not in current:
            if len(current) < 0.4 * len(baseline):
                return True
    return False
