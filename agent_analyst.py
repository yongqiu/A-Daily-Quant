"""
Multi-Agent Analyst Module
Orchestrates a debate between multiple AI agents with different personas to analyze a stock.
"""
import asyncio
import json
import logging
from typing import Dict, Any, List, AsyncGenerator
from datetime import datetime

# Import low-level API callers from llm_analyst
from llm_analyst import generate_analysis_openai, generate_analysis_gemini

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class StockAnalystAgent:
    """
    Represents a single specialized analyst agent.
    """

    def __init__(self, slug: str, name: str, role: str, description: str, system_prompt: str, template: str = None):
        self.slug = slug
        self.name = name
        self.role = role
        self.description = description
        self.system_prompt = system_prompt
        self.template = template

    async def analyze(self, context: str, api_config: Dict[str, Any]) -> str:
        """
        Perform analysis based on the agent's persona.
        """
        # Load Template if available
        prompt = ""
        if self.template:
            from jinja2 import Template
            t = Template(self.template)
            prompt = t.render(
                name=self.name, 
                role=self.role, 
                description=self.description, 
                context=context
            )
        else:
            # Fallback Legacy
            prompt = f"""
请你扮演【{self.name}】（{self.role}）。
你的核心职责是：{self.description}

{context}

请根据以上数据，给出你的专业分析意见。
要求：
1. 严格遵守你的人设，不要试图平衡观点，那是CIO的工作。
2. 观点必须鲜明，有理有据。
3. 如果数据不足以支持你的领域分析，直接指出。
4. 输出格式为Markdown，不要包含寒暄。
"""
        # Log the full prompt
        print(f"\n======== [Agent Prompt Debug: {self.name}] ========\n{prompt}\n===================================================\n")

        # Call LLM
        # We construct a fake stock_info/tech_data to satisfy the function signature if we reuse llm_analyst, 
        # OR we call the low-level functions directly. 
        # Calling low-level functions is better.
        
        provider = api_config.get('provider', 'openai')
        
        try:
            return await self._call_llm_direct(prompt, api_config)
                
        except Exception as e:
            logger.error(f"Agent {self.name} failed: {e}")
            return f"**{self.name} 分析失败**: {str(e)}"

    async def _call_llm_direct(self, prompt: str, api_config: Dict[str, Any]) -> str:
        """
        Direct LLM call bypassing llm_analyst's specific prompt construction logic.
        Supports OpenAI and Gemini.
        """
        provider = api_config.get('provider', 'openai')
        
        if provider == 'gemini':
            # Gemini Implementation
            try:
                # Lazy import to avoid dependency issues if not installed
                from google import genai
                from google.genai import types
                import os
                
                if api_config.get('credentials_path') and os.path.exists(api_config['credentials_path']):
                    os.environ['GOOGLE_APPLICATION_CREDENTIALS'] = api_config['credentials_path']
                
                client = genai.Client(
                    vertexai=True,
                    project=api_config['project_id'],
                    location=api_config['location']
                )
                
                response = client.models.generate_content(
                    model=api_config.get('model', 'gemini-2.5-flash'),
                    contents=prompt,
                    config=types.GenerateContentConfig(
                        temperature=0.3,
                        max_output_tokens=4096,
                        system_instruction=self.system_prompt
                    )
                )
                
                if hasattr(response, 'text'):
                    return response.text
                elif hasattr(response, 'candidates') and len(response.candidates) > 0:
                    candidate = response.candidates[0]
                    if hasattr(candidate, 'content') and hasattr(candidate.content, 'parts'):
                        return ''.join([part.text for part in candidate.content.parts if hasattr(part, 'text')])
                return str(response)
                
            except ImportError:
                return "Google Gen AI SDK not installed."
            except Exception as e:
                return f"Gemini API Error: {str(e)}"

        else:
            # OpenAI / DeepSeek / GLM Implementation
            try:
                from openai import OpenAI
                
                client = OpenAI(
                    api_key=api_config['api_key'],
                    base_url=api_config['base_url']
                )
                
                api_params = {
                    "model": api_config['model'],
                    "messages": [
                        {"role": "system", "content": self.system_prompt},
                        {"role": "user", "content": prompt}
                    ],
                    "temperature": 0.3,
                    "max_tokens": 4096
                }
                
                # Special handling for GLM thinking mode disable
                if provider == "glm":
                    api_params["extra_body"] = {"thinking": {"type": "disabled"}}

                response = client.chat.completions.create(**api_params)
                return response.choices[0].message.content
                
            except Exception as e:
                return f"OpenAI/Compatible API Error: {str(e)}"


class MultiAgentSystem:
    def __init__(self, api_config: Dict[str, Any]):
        self.api_config = api_config
        self.agents = []
        self._load_agents()

    def _load_agents(self):
        """Load agents configuration from database"""
        import database
        
        # Define the mapping of agents to DB slugs
        agent_configs = [
            {"slug": "agent_technician", "fallback_name": "技术派 (Technician)"},
            {"slug": "agent_risk_officer", "fallback_name": "风控官 (Risk Officer)"},
            {"slug": "agent_fundamentalist", "fallback_name": "基本面 (Fundamentalist)"}
        ]
        
        self.agents = []
        
        for cfg in agent_configs:
            strategy = database.get_strategy_by_slug(cfg['slug'])
            if strategy:
                self.agents.append(StockAnalystAgent(
                    slug=cfg['slug'],
                    name=strategy['name'],
                    role=strategy['params'].get('role', 'Experts'),
                    description=strategy.get('description', ''),
                    system_prompt=strategy['params'].get('system_prompt', ''),
                    template=strategy.get('template_content')
                ))
            else:
                # Add a dummy fallback or raise error
                print(f"⚠️ Warning: Agent strategy {cfg['slug']} not found in DB. Using fallback.")
                # This ensures system doesn't crash if DB init failed
                pass

        # Load CIO
        cio_slug = "agent_cio"
        strategy = database.get_strategy_by_slug(cio_slug)
        if strategy:
            self.cio = StockAnalystAgent(
                slug=cio_slug,
                name=strategy['name'],
                role=strategy['params'].get('role', 'CIO'),
                description=strategy.get('description', ''),
                system_prompt=strategy['params'].get('system_prompt', ''),
                template=strategy.get('template_content')
            )
        else:
             print(f"⚠️ Warning: CIO strategy {cio_slug} not found in DB.")


    async def run_debate_stream(self, stock_info: Dict[str, Any], tech_data: Dict[str, Any], realtime_data: Dict[str, Any], start_progress: int = 30) -> AsyncGenerator[str, None]:
        """
        Run the debate and yield SSE events.
        Format: JSON string for SSE data.
        """
        # 1. Prepare Basic Data (Common Context)
        asset_type = stock_info.get('asset_type', 'stock')
        
        # Fix Price 0 issue
        price = realtime_data.get('price')
        if not price or float(price) == 0:
             price = tech_data.get('close', 0)
        if not price or float(price) == 0:
             price = tech_data.get('realtime_price', 0)
        if (not price or float(price) == 0):
             if tech_data.get('ma5'): price = tech_data.get('ma5')
             elif tech_data.get('ma20'): price = tech_data.get('ma20')

        current_date = datetime.now().strftime('%Y-%m-%d')
        
        # Common Context (Shared by all)
        common_context = f"""
**分析对象**：{stock_info['name']} ({stock_info['symbol']}) [{asset_type.upper()}]
**分析日期**：{current_date}
**当前价格**：{price} (涨跌: {realtime_data.get('change_pct', 0)}%)
**市场大盘**：{realtime_data.get('market_index_price', 'N/A')} ({realtime_data.get('market_index_change', 0)}%)
"""

        # --- Enhanced Data Fetching ---
        news_context = ""
        funds_context = ""
        financial_context = ""
        
        try:
            from data_provider.akshare_fetcher import AkshareFetcher
            full_fetcher = AkshareFetcher(sleep_min=0.1, sleep_max=0.5)
            
            yield json.dumps({"type": "step", "content": "📡 正在并行获取：基本面数据、资金流向、最新资讯..."})
            
            # Run fetches in executor to verify non-blocking IO if possible, or just synchronous for now
            # In production, these should be async. Here we use sync calls but they are fast enough or worth waiting.
            
            # 1. News
            news_items = full_fetcher.get_stock_news(stock_info['symbol'])
            if news_items:
                news_context = "\n**近期重要资讯**：\n"
                for item in news_items[:3]:
                    news_context += f"- [{item['date']}] {item['title']}\n"
            
            # 2. Funds Flow (For Technician)
            funds_data = full_fetcher.fetch_money_flow(stock_info['symbol'])
            if funds_data and funds_data.get('status') == 'success':
                net_main = funds_data.get('net_amount_main', 0) / 10000.0 # 万
                net_main_str = f"{net_main:.2f}万" if abs(net_main) < 10000 else f"{net_main/10000:.2f}亿"
                
                funds_context = f"""
**资金流向数据**：
- 主力净流入：{net_main_str} (占比: {funds_data.get('net_pct_main', 0)}%)
- 超大单净流入：{funds_data.get('net_amount_super', 0)/10000:.2f}万
- 涨跌幅：{funds_data.get('change_pct', 0)}%
"""
            
            # 3. Financials (For Fundamentalist)
            reports_data = full_fetcher.fetch_financial_report(stock_info['symbol'])
            if reports_data and reports_data.get('data'):
                latest_date = reports_data.get('latest_date', 'N/A')
                latest_report = reports_data['data'].get(latest_date, {})
                
                # Extract key metrics if available (Handling potential key variations)
                # Akshare abstract often has: '归母净利润', '营业总收入', '净利润同比增长', etc.
                # Try to get raw dump of key fields
                financial_context = f"\n**核心财务数据 (最新报告期: {latest_date})**：\n"
                key_fields = ['营业总收入', '归母净利润', '扣非净利润', '基本每股收益', '净资产收益率']
                
                for k, v in latest_report.items():
                    for target in key_fields:
                        if target in k:
                            financial_context += f"- {k}: {v}\n"
                            
            yield json.dumps({"type": "step", "content": "✅ 多维度深度数据获取完成"})

        except Exception as e:
            logger.error(f"Enhanced fetch failed: {e}")
            yield json.dumps({"type": "step", "content": f"⚠️ 数据增强部分失败: {str(e)}"})

        # --- Construct Specialized Contexts ---
        
        # 1. Technician Context
        # Structure: K-Line Pattern, MA, Support/Resistance, Funds Flow, News
        pattern_str = ", ".join(tech_data.get('pattern_details', [])) or "无明显形态"
        tech_context = f"""
{common_context}

**技术面深度数据**：
- 均线系统：MA5={tech_data.get('ma5')}, MA20={tech_data.get('ma20')}, MA60={tech_data.get('ma60')}
- 均线排列：{tech_data.get('ma_arrangement', '未知')}
- K线形态：{pattern_str} (形态分: {tech_data.get('pattern_score', 0)})
- 相对强弱(RSI)：{tech_data.get('rsi', 'N/A')}
- 支撑/压力：支撑位 {tech_data.get('support', 'N/A')}, 压力位 {tech_data.get('resistance', 'N/A')}
- 波动率(ATR)：{tech_data.get('atr_pct', 'N/A')}%
{funds_context}
{news_context}
"""

        # 2. Fundamentalist Context
        # Structure: Valuation (PE/PB), Financials, Sector Rank, long-term trend (MA60)
        # Assuming realtime_data has PE/PB
        pe = realtime_data.get('pe_ratio', 'N/A')
        pb = realtime_data.get('pb_ratio', 'N/A')
        total_mv = realtime_data.get('total_mv', 'N/A')
        
        fund_context = f"""
{common_context}

**基本面深度数据**：
- 估值指标：PE(动态)={pe}, PB={pb}, 总市值={total_mv}
- 财务摘要：
{financial_context if financial_context else "暂无详细财报数据"}
- 长期趋势：MA60={tech_data.get('ma60')} (牛熊分界)
{news_context}
"""

        # 3. Risk Context
        # Structure: Volatility, Market Environment, Stop Loss, Position Sizing hints
        risk_context = f"""
{common_context}

**风控核心指标**：
- 波动率(ATR%)：{tech_data.get('atr_pct', 'N/A')}% (高波动需降仓)
- 市场环境：{realtime_data.get('market_index_change', 0)}% (大盘涨跌)
- 盈亏比评估：上方压力 {tech_data.get('resistance', 'N/A')} vs 下方支撑 {tech_data.get('support', 'N/A')}
- 乖离率：当前价格距离 MA20 {(float(price) - float(tech_data.get('ma20', price)))/float(tech_data.get('ma20', 1))*100:.2f}%
{news_context}
"""

        # Dispatcher Map
        context_map = {
            "agent_technician": tech_context,
            "agent_fundamentalist": fund_context,
            "agent_risk_officer": risk_context
        }

        yield json.dumps({"type": "progress", "value": start_progress, "message": "初始化多智能体辩论环境..."})
        yield json.dumps({"type": "step", "content": "🔔 辩论组建完毕，准备开始..."})
        yield json.dumps({"type": "token", "content": "\n\n# 🤖 AI 专家团队辩论纪要\n\n"})
        
        agent_results = []
        tasks = []
        total_agents = len(self.agents)
        current_progress = start_progress + 5
        yield json.dumps({"type": "progress", "value": current_progress, "message": "专家团队开始并行分析..."})

        for i, agent in enumerate(self.agents):
            # Select specific context or fallback to common
            my_context = context_map.get(agent.slug, common_context + news_context)
            tasks.append(agent.analyze(my_context, self.api_config))
        
        results = await asyncio.gather(*tasks)
        
        debate_content = ""
        progress_range_agents = 45
        
        for i, res in enumerate(results):
            agent = self.agents[i]
            inc = int(((i + 1) / total_agents) * progress_range_agents)
            progress_pct = current_progress + inc
            
            yield json.dumps({"type": "progress", "value": progress_pct, "message": f"{agent.name} 完成分析"})
            yield json.dumps({"type": "step", "content": f"✅ {agent.name} 提交了分析报告"})

            section_html = f"""
<details class="mb-3 group border border-gray-700/50 rounded-lg bg-gray-800/30 overflow-hidden">
    <summary class="cursor-pointer p-3 hover:bg-white/5 transition-colors flex items-center justify-between select-none list-none text-sm outline-none">
        <div class="flex items-center gap-2 font-bold text-indigo-300">
            <span>👤</span>
            <span>{agent.name} 分析报告</span>
        </div>
        <span class="text-xs text-gray-500 transition-transform duration-200 group-open:rotate-180">▼</span>
    </summary>
    <div class="p-4 pt-2 border-t border-dashed border-gray-700/50 text-sm text-gray-300 leading-relaxed font-sans mt-2">
{res.replace(chr(10), '<br/>')}
    </div>
</details>
<div class="h-2"></div>
"""
            debate_content += section_html
            yield json.dumps({"type": "token", "content": section_html})
            agent_results.append(f"【{agent.name}意见】:\n{res}")

        # 3. Round 2: CIO Decision
        yield json.dumps({"type": "step", "content": "🤔 首席投资官 (CIO) 正在汇总专家意见..."})
        yield json.dumps({"type": "progress", "value": 85, "message": "首席投资官 (CIO) 正在制定最终决策..."})
        
        # CIO sees Common Context + All Opinions
        cio_context = f"""
{common_context}
{news_context}

**专家团队辩论摘要**：
{''.join(agent_results)}

请根据以上信息，进行最终总结和决策。
"""
        cio_result = await self.cio.analyze(cio_context, self.api_config)
        
        yield json.dumps({"type": "progress", "value": 95, "message": "正在生成最终报告..."})
        yield json.dumps({"type": "step", "content": "✍️ CIO 正在签署最终裁决书..."})

        cio_header = "\n\n### 🎖️ 首席投资官 (CIO) 最终裁决\n\n"
        yield json.dumps({"type": "token", "content": cio_header})
        
        chunk_size = 8
        for i in range(0, len(cio_result), chunk_size):
            chunk = cio_result[i:i+chunk_size]
            yield json.dumps({"type": "token", "content": chunk})
            await asyncio.sleep(0.01)
            
        cio_section = cio_header + cio_result + "\n\n"
        full_report = debate_content + cio_section
        
        yield json.dumps({"type": "progress", "value": 100, "message": "分析完成"})
        yield json.dumps({"type": "final_html", "content": full_report})
        yield json.dumps({"type": "complete", "content": "Done"})
