"""Acceptance-only engine launcher: one internal failure and simulated cloud quota.

The actual model calls, specialist execution and verification remain production code.
This file is copied into a test-owned engine directory; never used by the product.
"""
import os
import json
from pathlib import Path
import runpy
import sys

config = json.loads(Path(__file__).with_name("acceptance.json").read_text(encoding="utf-8"))
source = Path(config["source"])
sys.path.insert(0, str(source))

from nl_coding_agent.agents.supervisor_executor import SupervisorMissionExecutor
from nl_coding_agent.agents import crew_backend
from nl_coding_agent.app.services import AppServices
from nl_coding_agent.core.permissions import CLOUD, grant
from nl_coding_agent.persistence import database

marker = Path(os.environ["NL_DATA_DIR"]) / "injected-internal-failure"
original_developer = SupervisorMissionExecutor.run_developer


def developer(self, state):
    if not marker.exists():
        marker.write_text("one internal executor failure before effects", encoding="utf-8")
        raise RuntimeError("Acceptance fixture: transient internal executor error")
    return original_developer(self, state)


SupervisorMissionExecutor.run_developer = developer

backend = crew_backend.CrewAIBackend
original_agent = backend.run_agent


def agent(self, spec, prompt, **kwargs):
    if kwargs.get("model_name") == "ollama/acceptance-cloud":
        (marker.parent / "injected-cloud-quota").write_text("429 quota", encoding="utf-8")
        raise RuntimeError("429 cloud quota exhausted (acceptance fixture)")
    return original_agent(self, spec, prompt, **kwargs)


backend.run_agent = agent
services = AppServices()
project = services.open_project(config["project"])
database.set_json_setting("supervisor.project." + str(project["id"]), {"pipeline": "flow"})
grant(CLOUD, project_id=project["id"], source="acceptance-fixture")
services._db.close()
runpy.run_path(str(source / "nl_agent.py"), run_name="__main__")
