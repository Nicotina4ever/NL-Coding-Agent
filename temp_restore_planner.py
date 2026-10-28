import sys, json
sys.path.insert(0, '.')
from pathlib import Path
b = json.load(open('data/mission_baselines/42.json'))
Path('nl_coding_agent/core/autonomous_roadmap_planner.py').write_text(b['nl_coding_agent/core/autonomous_roadmap_planner.py'], encoding='utf-8')
text = Path('nl_coding_agent/core/autonomous_roadmap_planner.py').read_text(encoding='utf-8')
old = '        if any(desc_short in c for c in completed):\n            continue\n        goal = f'
new = '        if any(desc_short in c for c in completed):\n            continue\n        if any(it["code"] in (m.get("goal") or "") or it["code"] in (m.get("title") or "") for m in list_missions() if m.get("status") == "completed"):\n            continue\n        goal = f'
text = text.replace(old, new)
Path('nl_coding_agent/core/autonomous_roadmap_planner.py').write_text(text, encoding='utf-8')
print('restored planner + duplicate guard')
