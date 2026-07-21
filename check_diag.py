from database.db import Database

db = Database("database/alphascan.db")

with db.connect() as conn:
    rows = conn.execute("""
        SELECT id, created_at, event_type, message
        FROM system_events
        WHERE event_type='ROBOT_DIAGNOSTIC'
        ORDER BY id DESC
        LIMIT 3
    """).fetchall()

print("Kayıt sayısı:", len(rows))

for row in rows:
    print(row)