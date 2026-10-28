"""Runner script for mandatory live Ollama multi-agent self-build delivery test."""
import sys
from pathlib import Path

# Add project root to path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from nl_coding_agent.agents.orchestrator import MultiAgentOrchestrator
from nl_coding_agent.persistence.missions import (
    create_mission,
    get_mission,
    get_tasks,
    get_handoffs,
    get_verification_runs,
)

goal = (
    "Create a new file nl_coding_agent/core/status.py containing function "
    "get_system_status_summary() -> dict that returns "
    "{'status': 'operational', 'engine': 'NL Coding Agent', 'version': '0.2.0'}. "
    "Create a test file tests/test_system_status.py that imports get_system_status_summary "
    "and tests that status is operational and version is 0.2.0."
)

m_id = create_mission(project_id=None, title="Self-Build Status Module", goal=goal)
print(f"=== LAUNCHING OLLAMA MULTI-AGENT MISSION #{m_id} ===")
print(f"Target repository: {ROOT}")
print(f"Goal: {goal}\n")

orch = MultiAgentOrchestrator(ROOT)
res = orch.run_mission(mission_id=m_id, goal=goal)

print("\n=== MISSION EXECUTION COMPLETED ===")
print("Status:", res.get("status"))
print("Git Diff Preview:\n", res.get("git_diff", "")[:1000])
print("\nReviewer Output:\n", res.get("review", ""))
print(f"Handoffs Recorded: {len(res.get('handoffs', []))}")
for h in res.get("handoffs", []):
    print(f"  - Handoff [{h['from_role']} -> {h['to_role']}]: {h['summary']}")
print(f"Verification Runs: {len(res.get('verification_runs', []))}")
for v in res.get("verification_runs", []):
    print(f"  - Verification ({'PASS' if v['passed'] else 'FAIL'}): {v['command']}")
