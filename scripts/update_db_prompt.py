
import pymysql
import json
import os

def get_db_config():
    if os.path.exists("config.json"):
        with open("config.json", 'r', encoding='utf-8') as f:
            config = json.load(f)
            return config.get('database', {})
    return {}

def get_connection():
    db_config = get_db_config()
    return pymysql.connect(
        host=db_config.get('host', 'localhost'),
        port=db_config.get('port', 3306),
        user=db_config.get('user', 'root'),
        password=db_config.get('password', ''),
        db=db_config.get('db', 'db_daily_strategy'),
        charset='utf8mb4',
        cursorclass=pymysql.cursors.DictCursor
    )

def update_prompt():
    conn = get_connection()
    try:
        new_template = """作为资深策略分析师，请根据收盘数据，制定明日交易计划。

**一、盘后复盘**
- **标的**：{{ stock_info.name }} ({{ stock_info.symbol }})
- **收盘**：{{ tech_data.close }} ({{ realtime_data.change_pct }}%)
- **形态**：{{ computed.ma_str }}
- **位置**：上方压力 {{ computed.res }} / 下方支撑 {{ computed.sup }}
- **资金**：{{ computed.funds_str }}

**二、明日推演**
1. **评分解读**：当前评分 {{ tech_data.composite_score }}，结合技术面判断强弱。
2. **多空博弈**：根据资金流向推测主力意图（试盘/出货/吸筹）。
3. **情景预演**：
    - **情景A（向上突破）**：关键点位及确认信号。
    - **情景B（向下调整）**：低吸机会或破位风险。

**三、交易计划**
请输出 JSON 格式的交易触发条件（请确保 JSON 格式合法，不要包含注释）：
```json
{
    "buy_trigger": "突破 xx 元 或 回踩 xx 元企稳",
    "buy_price_max": "xx.xx",
    "buy_dip_price": "xx.xx",
    "stop_loss_price": "xx.xx",
    "take_profit_target": "xx.xx",
    "risk_rating": "高/中/低"
}
```"""
        
        with conn.cursor() as cursor:
            # Check if strategy exists
            cursor.execute("SELECT id FROM strategies WHERE slug = 'deep_monitor'")
            if cursor.fetchone():
                print("Updating existing strategy 'deep_monitor'...")
                cursor.execute(
                    "UPDATE strategies SET template_content = %s, updated_at = NOW() WHERE slug = 'deep_monitor'",
                    (new_template,)
                )
            else:
                print("Strategy 'deep_monitor' not found! Creating it...")
                cursor.execute(
                    """INSERT INTO strategies (slug, name, description, category, template_content)
                       VALUES ('deep_monitor', '深度复盘', '盘后分析与明日计划', 'analysis', %s)""",
                    (new_template,)
                )
            
            conn.commit()
            print("Successfully updated deep_monitor prompt.")
            
    except Exception as e:
        print(f"Error: {e}")
    finally:
        conn.close()

if __name__ == "__main__":
    update_prompt()
