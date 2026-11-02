"""P3 sub-agents: isolation, structured handoff parsing and advisor execution."""
from __future__ import annotations

import json

from nl_coding_agent.agents.crew_backend import FakeCrewRuntime
from nl_coding_agent.agents.subagents import SubagentRunner, _parse_handoff


def test_parse_handoff_prefers_structured_json():
    text = ("Analysis text.\n```json\n"
            '{"summary": "Use a guard", "facts": ["f1"], "decisions": ["d1"], '
            '"risks": ["r1"], "next_steps": ["n1"]}\n```')
    handoff = _parse_handoff(text, name="advisor")
    assert handoff["summary"] == "Use a guard"
    assert handoff["facts"] == ["f1"]
    assert handoff["decisions"] == ["d1"]
    assert _parse_handoff("plain text", name="advisor")["summary"] == "plain text"


def test_subagent_context_is_isolated_and_read_only(tmp_path):
    root = tmp_path / "project"
    (root / "src").mkdir(parents=True)
    (root / "src" / "calc.py").write_text("def add(a, b):\n    return a + b\n")
    runtime = FakeCrewRuntime({
        "advisor": ["```json\n{\"summary\": \"isolated finding\", \"risks\": [\"r\"]}\n```"],
    })
    runner = SubagentRunner(root, None, runtime)
    result = runner.run(name="Security Advisor", objective="Review src/calc.py",
                        context="ONLY THIS CONTEXT", model="ollama/advisor",
                        instructions="Look for injection risks.")
    assert result.handoff["summary"] == "isolated finding"
    assert result.handoff["risks"] == ["r"]
    call = runtime.calls[-1]
    assert "ONLY THIS CONTEXT" in call["prompt"]
    assert "Look for injection risks." in call["backstory"]
    tool_names = {getattr(tool, "name", "") for tool in call["tools"]}
    assert "write_file" not in tool_names and "patch_file" not in tool_names
    assert "read_file" in tool_names


def test_subagent_allowed_tools_are_restricted(tmp_path):
    root = tmp_path / "project"
    root.mkdir()
    runtime = FakeCrewRuntime({"advisor": ["ok"]})
    runner = SubagentRunner(root, None, runtime)
    runner.run(name="A", objective="B", context="C",
               allowed_tools=["read_file"])
    names = {getattr(tool, "name", "") for tool in runtime.calls[-1]["tools"]}
    assert names == {"read_file"}
