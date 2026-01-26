import database
import json

def inspect_analysis(symbol="603685"):
    print(f"Inspecting DB records for {symbol}...")
    
    # 1. Inspect holding_analysis
    print("\n--- table: holding_analysis ---")
    data = database.get_holding_analysis(symbol, mode='multi_agent')
    if data:
        print(json.dumps(data, indent=2, default=str))
        if data.get('price') == 0:
            print("⚠️ ALERT: Stored price is 0!")
        else:
            print("✅ Stored price is valid.")
    else:
        print("❌ No data found in holding_analysis")
        
    # 2. Inspect daily_metrics
    print("\n--- table: daily_metrics ---")
    conn = database.get_connection()
    try:
        with conn.cursor() as cursor:
            cursor.execute("SELECT * FROM daily_metrics WHERE symbol = %s ORDER BY date DESC LIMIT 1", (symbol,))
            row = cursor.fetchone()
            if row:
                print(f"Date: {row['date']}, Price: {row.get('price')}, Change: {row.get('change_pct')}%")
                if row.get('price') == 0:
                     print("⚠️ ALERT: Metrics price is 0!")
            else:
                print("❌ No metrics found.")
    finally:
        conn.close()

if __name__ == "__main__":
    inspect_analysis("603685")