import sys, re
sys.path.insert(0, '.')
path = 'nl_coding_agent/core/autonomous_roadmap_planner.py'
text = open(path, encoding='utf-8').read()
old = '        if any(desc_short in c for c in completed):\n            continue'
new = '        if any(desc_short in c for c in completed):\n            continue\n        if any(it["code"] in (m.get("goal") or "") or it["code"] in (m.get("title") or "") for m in list_missions() if m.get("status") == "completed"):\n            continue'
text = text.replace(old, new)
open(path, 'w', encoding='utf-8').write(text)
print('fixed')
