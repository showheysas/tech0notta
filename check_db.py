import sqlite3
import os

db_path = "meeting_notes.db"

if not os.path.exists(db_path):
    print(f"Database file not found at {db_path}")
else:
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    try:
        cursor.execute("SELECT * FROM jobs")
        rows = cursor.fetchall()
        print(f"Total jobs: {len(rows)}")
        for row in rows:
            print(row)
    except Exception as e:
        print(f"Error querying database: {e}")
    finally:
        conn.close()
