import sys; sys.path.insert(0, '.')
from nl_coding_agent.persistence.database import init_db
conn = init_db()
with conn:
    conn.execute("UPDATE missions SET title = ? WHERE id = 43",
                 ("Supervisor Persistente — verify continuous autonomous backlog execution without manual repair",))
conn.close()
print('updated 43 title')
