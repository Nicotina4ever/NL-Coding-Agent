import tempfile
import unittest
from pathlib import Path

from nl_coding_agent.agents.orchestrator import (
    clean_file_content,
    parse_reviewer_verdict,
)
from nl_coding_agent.core.roadmap import (
    extract_paths,
    format_mission,
    next_mission,
)
from nl_coding_agent.core.workspace import (
    diff_snapshots,
    out_of_scope_paths,
    path_in_scope,
    snapshot_workspace,
)


class TestRoadmap(unittest.TestCase):
    def test_repository_roadmap_parses(self):
        mission = next_mission(Path(__file__).resolve().parents[1])
        self.assertIn("NL Code 1.0 STABLE", mission["title"])
        self.assertIn("nl_coding_agent/context/", mission["write_paths"])
        self.assertIn("nl_coding_agent/agents/orchestrator.py", mission["write_paths"])
        self.assertIn("nl_coding_agent/app/chat_tools.py", mission["write_paths"])
        self.assertIn("tests/test_context_engine.py", mission["write_paths"])
        self.assertIn("docs/NL_CODE_1_0_STABLE_PIANO_OPERATIVO.md", mission["write_paths"])
        self.assertGreaterEqual(len(mission["write_paths"]), 4)
        self.assertGreaterEqual(len(mission["acceptance_gates"]), 5)
        self.assertIn("Objective:", mission["goal"])
        self.assertIn("Acceptance gates:", mission["goal"])
        self.assertIn("Title:", format_mission(mission))

    def test_extract_paths_ignores_protected_and_urls(self):
        text = (
            "Modify `nl_coding_agent/core/roadmap.py`, `tests/test_roadmap.py`, and "
            "`pyproject.toml`. Never touch `python/python.exe` or `crewAI/crewai.py`. "
            "See https://example.com/some/file.py and "
            "`docs/NL_CODE_1_0_STABLE_PIANO_OPERATIVO.md`."
        )
        paths = extract_paths(text)
        self.assertIn("nl_coding_agent/core/roadmap.py", paths)
        self.assertIn("tests/test_roadmap.py", paths)
        self.assertIn("pyproject.toml", paths)
        self.assertIn("docs/NL_CODE_1_0_STABLE_PIANO_OPERATIVO.md", paths)
        self.assertNotIn("python/python.exe", paths)
        self.assertNotIn("crewAI/crewai.py", paths)

    def test_next_mission_requires_document(self):
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaises(FileNotFoundError):
                next_mission(tmp)


class TestReviewerVerdict(unittest.TestCase):
    def test_verdicts(self):
        self.assertEqual(parse_reviewer_verdict("APPROVE\nLooks good."), "APPROVE")
        self.assertEqual(parse_reviewer_verdict("**APPROVED** — clean diff."), "APPROVE")
        self.assertEqual(parse_reviewer_verdict("REJECT: missing tests"), "REJECT")
        self.assertEqual(parse_reviewer_verdict("Verdict: APPROVE\nok"), "APPROVE")
        self.assertEqual(parse_reviewer_verdict("The code looks fine to me"), "REJECT")


class TestFileContentCleaning(unittest.TestCase):
    def test_strips_fences(self):
        raw = "```python\nprint('hi')\n```"
        self.assertEqual(clean_file_content(raw, "a.py"), "print('hi')\n")

    def test_salvages_unified_diff(self):
        raw = (
            "diff --git a/a.py b/a.py\n"
            "--- a/a.py\n"
            "+++ b/a.py\n"
            "@@ -1 +1 @@\n"
            "-old\n"
            "+new\n"
        )
        self.assertIn("new", clean_file_content(raw, "a.py"))
        self.assertNotIn("diff --git", clean_file_content(raw, "a.py"))


class TestWorkspaceScopes(unittest.TestCase):
    def test_snapshot_and_diff(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "a.py").write_text("x = 1\n", encoding="utf-8")
            before = snapshot_workspace(root)
            (root / "a.py").write_text("x = 2\n", encoding="utf-8")
            (root / "b.py").write_text("y = 1\n", encoding="utf-8")
            after = snapshot_workspace(root)
            diff, changed = diff_snapshots(before, after)
            self.assertIn("a.py", changed)
            self.assertIn("b.py", changed)
            self.assertIn("-x = 1", diff)
            self.assertIn("+x = 2", diff)

    def test_scopes(self):
        self.assertTrue(path_in_scope("nl_coding_agent/core/a.py", ["nl_coding_agent/"]))
        self.assertTrue(path_in_scope("tests/test_a.py", ["tests/test_a.py"]))
        self.assertTrue(path_in_scope("docs/a.md", ["docs/*.md"]))
        self.assertFalse(path_in_scope("python/python.exe", ["nl_coding_agent/"]))
        self.assertEqual(
            out_of_scope_paths(["nl_coding_agent/a.py", "python/x.py"], ["nl_coding_agent/"]),
            ["python/x.py"],
        )


if __name__ == "__main__":
    unittest.main()
