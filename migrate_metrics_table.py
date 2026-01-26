import pymysql
import json
import database

def migrate_metrics_table():
    print("🚀 Starting daily_metrics table migration...")
    
    conn = database.get_connection()
    try:
        with conn.cursor() as cursor:
            # 1. Check existing columns
            cursor.execute("DESCRIBE daily_metrics")
            columns = [row['Field'] for row in cursor.fetchall()]
            
            # 2. Add new columns if missing
            new_cols = {
                'score_breakdown': "JSON",
                'score_details': "JSON",
                'operation_suggestion': "TEXT",
                'stop_loss_suggest': "DECIMAL(10, 2)",
                'atr_pct': "DECIMAL(10, 2)",
                'price_vs_high120': "DECIMAL(10, 4)"
            }
            
            for col, dtype in new_cols.items():
                if col not in columns:
                    print(f"➕ Adding column: {col} ({dtype})")
                    cursor.execute(f"ALTER TABLE daily_metrics ADD COLUMN {col} {dtype}")
                else:
                    print(f"✅ Column {col} already exists.")
            
            conn.commit()
            print("🎉 Migration completed successfully!")
            
    except Exception as e:
        print(f"❌ Migration failed: {e}")
    finally:
        conn.close()

if __name__ == "__main__":
    migrate_metrics_table()