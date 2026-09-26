import sys
sys.path.insert(0, 'backend')

from app.database.mongodb import get_database

db = get_database()
col = db['activity_events']

total = col.count_documents({})
print(f'Total events in activity_events collection: {total}')

# Group by session_id, show recent sessions
pipeline = [
    {"$group": {"_id": "$session_id", "count": {"$sum": 1}}},
    {"$sort": {"_id": -1}},
    {"$limit": 10}
]
sessions = list(col.aggregate(pipeline))
print(f'Most recent sessions (up to 10):')
for s in sessions:
    print(f'  {s["_id"]:45s}  events={s["count"]}')

# Check the 3 latest session-XXXXXXXX-DATE sessions (from demo agent)
agent_sessions = [s for s in sessions if s["_id"].startswith("session-") and "-2026-09-26" in s["_id"]]
print(f'\nAgent sessions today: {len(agent_sessions)}')
for s in agent_sessions:
    # Verify sequence in each session
    events = list(col.find({"session_id": s["_id"]}).sort("timestamp", 1))
    actions = [e.get("action") for e in events]
    print(f'  {s["_id"]}:')
    print(f'    Actions: {actions}')
