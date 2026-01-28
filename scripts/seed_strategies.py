import sys
import os

# Add parent directory to path to import database module
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from database import get_connection

def seed_strategies():
    strategies = [
        {
            "slug": "stock_holding_risk",
            "name": "个股风控 (Stock Holding Risk)",
            "description": "针对持仓股票的严格风控策略，重点关注止损位和趋势破位。",
            "category": "holding",
            "template_content": """作为严格的A股风险控制官，你的首要任务是保护资本。请基于以下数据对持仓进行风控评估。

**标的：** {{ stock_info.name }} ({{ stock_info.symbol }})
**现价：** ¥{{ tech_data.close }} (成本: ¥{{ stock_info.cost_price | default(0) }})

**技术指标：**
- MA20 (趋势线): {{ tech_data.ma20 }}
- MA60 (牛熊线): {{ tech_data.ma60 }}
- 盈亏比例: {{ ((tech_data.close - stock_info.cost_price)/stock_info.cost_price*100) | round(2) }}%

**分析任务：**
1. **趋势健康度**：当前价格是否在MA20之上？是否存在破位风险？
2. **止损建议**：如果当前处于亏损或利润回撤，应该在哪里坚决止损？
3. **加减仓建议**：当前位置适合加仓、减仓还是持股不动？

**输出要求：**
- **操作指令**：(持有 / 减仓 / 清仓 / 观望)
- **风控位**：给出明确的止损价格。
- **简述理由**：用一句话概括。"""
        },
        {
            "slug": "etf_holding_steady",
            "name": "ETF定投 (ETF Steady)",
            "description": "针对ETF的长期稳健策略，适合网格交易和定投。",
            "category": "holding",
            "template_content": """作为稳健的资产配置专家，请分析该ETF走势。

**标的：** {{ stock_info.name }} ({{ stock_info.symbol }})
**现价：** {{ tech_data.close }}

**核心逻辑：**
- 价格 > MA20: 持有或定投
- 价格 < MA20: 暂停定投或观望
- 价格 < MA60: 考虑避险

**趋势数据：**
- MA20: {{ tech_data.ma20 }}
- MA60: {{ tech_data.ma60 }}

请给出针对ETF的操作建议（持有/定投/止盈/观望）。"""
        },
        {
            "slug": "candidate_growth",
            "name": "成长股挖掘 (Candidate Growth)",
            "description": "针对候选股票的成长性挖掘，关注基本面和技术面共振。",
            "category": "candidate",
            "template_content": """作为投资经理，请评估该股票的买入机会。

**标的：** {{ stock_info.name }} ({{ stock_info.symbol }})
**现价：** {{ tech_data.close }}

**评分：** {{ tech_data.composite_score }} 分
**量比：** {{ tech_data.volume_ratio }}

请从技术面（均线、形态）和资金面分析，该股是否具备买入价值？如果是，建议的买入区间是多少？"""
        },
        {
            "slug": "speculator_mode",
            "name": "游资连板 (Speculator Mode)",
            "description": "模拟顶级游资思维，关注情绪、资金流和板块地位。",
            "category": "candidate",
            "template_content": """# Role
你是一名拥有20年实战经验的A股顶级游资操盘手，擅长量价分析、情绪周期研判及通过盘口语言洞察主力意图。

# Context
**标的：** {{ stock_info.name }} ({{ stock_info.symbol }})
**现价：** ¥{{ tech_data.close }} (涨幅: {{ tech_data.change_pct }}%)
**量比：** {{ tech_data.volume_ratio }}
**板块：** {{ tech_data.sector }} (Rank: {{ tech_data.rank_in_sector | default('N/A') }})

# Task
1. **地位定性**：判断该股是龙几？
2. **多空博弈**：主力是在出货还是接力？
3. **剧本推演**：明日高开/低开怎么做？

# Output
给出【操作评级】、【逻辑摘要】、【剧本推演】。"""
        },
        {
            "slug": "realtime_intraday",
            "name": "盘中盯盘 (Realtime Intraday)",
            "description": "实时盘中监控，针对异动进行快速点评。",
            "category": "realtime",
            "template_content": """作为实战派交易员，正在进行盘中监控。

**标的：** {{ stock_info.name }}
**实时价：** {{ realtime_data.price }} (涨跌: {{ realtime_data.change_pct }}%)
**量比：** {{ realtime_data.volume_ratio }}

**参考指标：**
- MA20: {{ tech_data.ma20 }}
- 压力位: {{ tech_data.pressure | default('N/A') }}
- 支撑位: {{ tech_data.support | default('N/A') }}

**判断：**
当前分时走势是强是弱？是否存在诱多/诱空？
给出即时操作建议（追涨/止盈/低吸/观望）。"""
        },
          {
            "slug": "deep_monitor",
            "name": "深度盘口诊断 (Deep Monitor)",
            "description": "结合资金流、龙虎榜和板块效应的深度实时分析。",
            "category": "realtime",
            "template_content": """作为资深策略分析师，请进行盘中深度评估。

**一、情报**
- **标的**：{{ stock_info.name }} ({{ realtime_data.change_pct }}%)
- **资金**：主力净入 {{ realtime_data.money_flow.net_amount_main | default(0) }}
- **板块**：{{ tech_data.sector }} ({{ tech_data.sector_change }}%)
- **大盘**：{{ realtime_data.market_index_status }}

**二、分析**
1. **评分解读**：Score {{ tech_data.composite_score }}
2. **资金博弈**：主力意图分析
3. **环境共振**：个股是否顺势？

**三、结论**
给出行情剧本推演（向上突破/向下破位）及操作建议。"""
        },
        {
            "slug": "realtime_crypto",
            "name": "Crypto实时 (Crypto Realtime)",
            "description": "加密货币7x24小时实时策略，关注波动率和突破。",
            "category": "realtime",
            "template_content": """作为币圈交易员(Degen)，分析当前行情。

**标的：** {{ stock_info.name }}
**价格：** ${{ realtime_data.price }} (24h: {{ realtime_data.change_pct }}%)

**技术面：**
- MA20: ${{ tech_data.ma20 }}
- ATR波动: {{ tech_data.atr_pct }}%

**指令：**
1. **多空研判**：Trend is King.
2. **操作建议**：Long / Short / Wait
3. **止损位**：严格止损。"""
        },
        {
            "slug": "realtime_future",
            "name": "期货实时 (Future Realtime)",
            "description": "期货日内策略，关注杠杆风险和关键点位。",
            "category": "realtime",
            "template_content": """作为期货交易员，分析盘面。

**合约：** {{ stock_info.name }}
**价格：** {{ realtime_data.price }} ({{ realtime_data.change_pct }}%)

**关键位：**
- MA5: {{ tech_data.ma5 }}
- 压力: {{ tech_data.resistance }}
- 支撑: {{ tech_data.support }}

**策略：**
给出开多/开空/平仓建议，并明确止损点。"""
        },
        {
            "slug": "crypto_holding",
            "name": "Crypto持仓 (Crypto Holding)",
            "description": "加密货币持仓分析（日报模式）。",
            "category": "holding",
            "template_content": """分析Crypto持仓趋势。

**标的：** {{ stock_info.name }}
**价格：** ${{ tech_data.close }}

**指标：**
- RSI: {{ tech_data.rsi }}
- Bollinger: {{ tech_data.boll_position }}%

判断当前是多头还是空头趋势，建议继续持有还是止损离场？"""
        },
        {
            "slug": "future_holding",
            "name": "期货持仓 (Future Holding)",
            "description": "期货持仓分析（日报模式）。",
            "category": "holding",
            "template_content": """分析期货持仓风险。

**合约：** {{ stock_info.name }}
**价格：** {{ tech_data.close }}
**MACD：** {{ tech_data.macd_signal }}

判断趋势延续性，建议加仓、减仓还是平仓？"""
        }
    ]

    conn = get_connection()
    try:
        with conn.cursor() as cursor:
            # Create/Update Strategies
            for s in strategies:
                print(f"Processing strategy: {s['name']}")
                
                # Check if exists
                cursor.execute("SELECT id FROM strategies WHERE slug = %s", (s['slug'],))
                existing = cursor.fetchone()
                
                if existing:
                    strategy_id = existing['id']
                    # Optional: Update template if you want to force reset, or just skip
                    # Here we update default description and category, but maybe keep user template?
                    # For now, let's update everything to ensure sync with codebase logic
                    cursor.execute("""
                        UPDATE strategies 
                        SET name=%s, description=%s, category=%s, template_content=%s
                        WHERE id=%s
                    """, (s['name'], s['description'], s['category'], s['template_content'], strategy_id))
                else:
                    cursor.execute("""
                        INSERT INTO strategies (slug, name, description, category, template_content)
                        VALUES (%s, %s, %s, %s, %s)
                    """, (s['slug'], s['name'], s['description'], s['category'], s['template_content']))
                    strategy_id = cursor.lastrowid
                
                # Add default params if any (Example)
                # if s['slug'] == 'stock_holding_risk':
                #     cursor.execute("INSERT IGNORE INTO strategy_params ...")

        conn.commit()
        print("✅ Strategies seeded successfully.")
    except Exception as e:
        print(f"❌ Error seeding strategies: {e}")
    finally:
        conn.close()

if __name__ == "__main__":
    seed_strategies()
