import pymysql
import json
import os
from datetime import datetime

CONFIG_FILE = "config.json"

def get_db_config():
    if os.path.exists(CONFIG_FILE):
        try:
            with open(CONFIG_FILE, 'r', encoding='utf-8') as f:
                config = json.load(f)
                return config.get('database', {})
        except Exception as e:
            print(f"Error loading config: {e}")
    return {}

def get_connection():
    db_config = get_db_config()
    print(f"DB Config: {db_config}")
    if not db_config:
        db_config = {
            'host': 'localhost',
            'user': 'root',
            'password': '',
            'db': 'db_daily_strategy',
            'port': 3306
        }
    
    return pymysql.connect(
        host=db_config.get('host', 'localhost'),
        port=db_config.get('port', 3306),
        user=db_config.get('user', 'root'),
        password=db_config.get('password', ''),
        db=db_config.get('db', 'db_daily_strategy'),
        charset='utf8mb4',
        cursorclass=pymysql.cursors.DictCursor
    )

def inspect_selections():
    try:
        conn = get_connection()
        with conn.cursor() as cursor:
            # Check table existence
            cursor.execute("SHOW TABLES LIKE 'daily_selections'")
            if not cursor.fetchone():
                print("Table 'daily_selections' does not exist!")
                return

            # Check rows count
            cursor.execute("SELECT COUNT(*) as count FROM daily_selections")
            count = cursor.fetchone()['count']
            print(f"Total rows in daily_selections: {count}")

            # Get latest dates
            cursor.execute("SELECT DISTINCT selection_date FROM daily_selections ORDER BY selection_date DESC LIMIT 5")
            dates = cursor.fetchall()
            print("Latest dates:", [d['selection_date'].strftime('%Y-%m-%d') for d in dates])
            
            if dates:
                latest_date = dates[0]['selection_date']
                print(f"Fetching selections for {latest_date}...")
                cursor.execute("SELECT * FROM daily_selections WHERE selection_date = %s", (latest_date,))
                rows = cursor.fetchall()
                for row in rows:
                    print(f" - {row['symbol']} {row['name']} Score: {row['composite_score']}")

    except Exception as e:
        print(f"Error: {e}")
    finally:
        if 'conn' in locals():
            conn.close()

if __name__ == "__main__":
    inspect_selections()