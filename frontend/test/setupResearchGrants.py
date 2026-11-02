"""Prepare a scratch engine project with the Project Access grant for URL tests.

This is test setup using the existing backend permission API; the extension
itself never grants permissions. It writes only inside NL_DATA_DIR.
"""
import json
import os
import sys
from pathlib import Path

repo = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(repo))

from nl_coding_agent.app.services import AppServices
from nl_coding_agent.core import permissions

project_dir = Path(sys.argv[1]).resolve()
services = AppServices()
try:
    project = services.open_project(project_dir)
    project_id = int(project["id"])
    services.set_permission_scope(
        permissions.NETWORK, True, project_id=project_id, source="acceptance")
    print(json.dumps({
        "project_id": project_id,
        "network": permissions.get_policy(project_id).get("network"),
        "grants": len(permissions.list_capability_grants("web-fetch")),
    }))
finally:
    services._db.close()
