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
    def __init__(self, name: str, role: str, description: str, system_prompt: str):
        self.name = name
        self.role = role
        self.description = description
        self.system_prompt = system_prompt

    async def analyze(self, context: str, api_config: Dict[str, Any]) -> str:
        """
        Perform analysis based on the agent's persona.
        """
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
            if provider == 'gemini':
                # Map config for Gemini
                response = generate_analysis_gemini(
                    stock_info={},  # Not used directly if we override logic, but wait, the low level func builds prompt.
                    # We might need to call client directly if we want custom prompts.
                    # Let's bypass generate_analysis_gemini's prompt building if possible
                    # checking llm_analyst.py... create_analysis_prompt is called inside.
                    # This implies we cannot easily reuse generate_analysis_gemini for custom prompts without modification.
                    # To avoid modifying llm_analyst heavily, I will implement a simple direct caller here based on llm_analyst's implementation.
                    tech_data={}, 
                    project_id=api_config['project_id'],
                    location=api_config['location'],
                    credentials_path=api_config.get('credentials_path'),
                    model=api_config.get('model', 'gemini-2.5-flash'),
                    analysis_type="custom_agent", # Hack: We need to handle this in llm_analyst OR implement call here.
                    realtime_data=None 
                )
                # Wait, generate_analysis_gemini calls create_analysis_prompt inside.
                # If analysis_type is unknown, create_analysis_prompt might fail or return default.
                # It's better to implement a simple_call_llm here.
                return await self._call_llm_direct(prompt, api_config)

            else:
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
        self.agents = [
            StockAnalystAgent(
                name="技术派 (Technician)",
                role="技术分析专家",
                description="你是一名纯粹的技术分析师。你只相信图形、趋势、均线（MA）、量价配合（Volume）和动量指标（RSI/MACD）。",
                system_prompt="你是一名严谨的技术分析师。我不关心基本面，也不关心宏观新闻。我只看价格行为(Price Action)。如果价格跌破均线，就是卖出信号。如果放量突破，就是买入信号。"
            ),
            StockAnalystAgent(
                name="风控官 (Risk Officer)",
                role="风险控制专家",
                description="你是团队中的刹车片。你极度厌恶风险。你关注波动率（ATR）、最大回撤、盈亏比（R:R）。你的任务是寻找任何可能导致亏损的理由。",
                system_prompt="你是一名苛刻的风险控制官。你的职责是泼冷水。我们要保护本金。任何未经确认的上涨都是诱多。任何指标背离都是陷阱。你要指出最坏的情况。"
            ),
            StockAnalystAgent(
                name="基本面 (Fundamentalist)",
                role="基本面与逻辑分析师",
                description="你关注资产背后的逻辑。如果是股票，你关注题材、业绩、新闻催化剂。如果是ETF，你关注行业周期。如果是Crypto/期货，你关注宏观情绪。",
                system_prompt="你是一名具有大局观的研究员。你关注长期逻辑和市场叙事(Narrative)。忽略短期的K线噪音，寻找驱动价格上涨的核心逻辑。"
            )
        ]
        self.cio = StockAnalystAgent(
            name="CIO (首席投资官)",
            role="决策者",
            description="你是最终决策者。你需要综合各方专家的意见，做出最终的买卖裁决。",
            system_prompt="你是一只基金的首席投资官。你需要听取技术派、风控官和基本面研究员的辩论。你的任务是：1. 总结各方观点。 2. 平衡收益与风险。 3. 给出最终的、明确的操作指令（买入/持有/减仓/空仓）。 4. 制定交易计划（仓位、止损位）。不要模棱两可。"
        )

    async def run_debate_stream(self, stock_info: Dict[str, Any], tech_data: Dict[str, Any], realtime_data: Dict[str, Any], start_progress: int = 30) -> AsyncGenerator[str, None]:
        """
        Run the debate and yield SSE events.
        Format: JSON string for SSE data.
        """
        # 1. Prepare Context
        asset_type = stock_info.get('asset_type', 'stock')
        
        # Fix Price 0 issue: Prioritize realtime, fallback to history close if 0 or None
        price = realtime_data.get('price')
        
        # Ensure we treat 0.0 as invalid
        if not price or float(price) == 0:
             price = tech_data.get('close', 0)
        
        # If still 0, try fallbacks
        if not price or float(price) == 0:
             # Try other potential keys
             price = tech_data.get('realtime_price', 0)

        # Last resort: Use MA5 or MA20 as proxy if price is completely missing but indicators exist
        # This prevents "Price: 0.0" which confuses LLM
        if (not price or float(price) == 0):
             if tech_data.get('ma5'):
                 price = tech_data.get('ma5')
             elif tech_data.get('ma20'):
                 price = tech_data.get('ma20')

        # Fix Date issue: Provide explicit date
        current_date = datetime.now().strftime('%Y-%m-%d')
        
        # 获取K线形态
        pattern_score = tech_data.get('pattern_score', 0)
        pattern_details = tech_data.get('pattern_details', [])
        pattern_str = "无"
        if pattern_details:
             pattern_str = ", ".join(pattern_details) + f" (修正分: {pattern_score})"

        context = f"""
**分析对象**：{stock_info['name']} ({stock_info['symbol']}) [{asset_type.upper()}]
**分析日期**：{current_date}
**当前价格**：{price} (涨跌: {realtime_data.get('change_pct', 0)}%)

**技术指标概览**：
- MA20: {tech_data.get('ma20', 'N/A')}
- MA60: {tech_data.get('ma60', 'N/A')}
- RSI: {tech_data.get('rsi', 'N/A')}
- K线形态: {pattern_str}
- 量比: {realtime_data.get('volume_ratio', 'N/A')}
- 波动率(ATR%): {tech_data.get('atr_pct', 'N/A')}%

**市场环境**：
- 大盘指数：{realtime_data.get('market_index_price', 'N/A')} ({realtime_data.get('market_index_change', 0)}%)
"""
        yield json.dumps({"type": "progress", "value": start_progress, "message": "初始化多智能体辩论环境..."})
        yield json.dumps({"type": "step", "content": "🔔 辩论组建完毕，准备开始..."})
        
        # We start with the CIO section placeholder or header
        yield json.dumps({"type": "token", "content": "\n\n# 🤖 AI 专家团队辩论纪要\n\n"})
        
        agent_results = []
        
        # 2. Round 1: Parallel Analysis
        tasks = []
        total_agents = len(self.agents)
        
        # Send initial progress for analysis start
        current_progress = start_progress + 5
        yield json.dumps({"type": "progress", "value": current_progress, "message": "专家团队开始并行分析..."})

        for i, agent in enumerate(self.agents):
            tasks.append(agent.analyze(context, self.api_config))
        
        # Wait for all (Parallel)
        results = await asyncio.gather(*tasks)
        
        debate_content = ""
        
        # Allocate 40% of progress bar for agents analysis (e.g., 35% -> 75%)
        # But allow some room for CIO. Let's say agents take us to 80%.
        # If start is 35, remaining is 65.
        # Agents phase: 35 -> 80 (delta 45)
        # CIO phase: 80 -> 95 (delta 15)
        
        progress_range_agents = 45
        
        # Process results with incremental progress updates
        for i, res in enumerate(results):
            agent = self.agents[i]
            # Calculate incremental progress
            inc = int(((i + 1) / total_agents) * progress_range_agents)
            progress_pct = current_progress + inc
            
            yield json.dumps({"type": "progress", "value": progress_pct, "message": f"{agent.name} 完成分析"})
            yield json.dumps({"type": "step", "content": f"✅ {agent.name} 提交了分析报告"})

            # Format: Use HTML <details> for cleaner UI, so it's not one huge text block
            # But the user also wants to see it.
            # Let's use a nice blockquote or custom div structure if markdown supports it.
            # Using blockquote `> ` is standard.
            
            section_header = f"### 👤 {agent.name}\n"
            section_body = f"{res}\n\n"
            
            # Wrap in a way that looks like a card in Markdown?
            # We can use HTML directly since we render HTML.
            section_html_wrapper = f"""
<div class="agent-card mb-4 p-4 bg-gray-800/50 rounded-lg border border-gray-700">
    <div class="font-bold text-indigo-300 mb-2 border-b border-gray-700 pb-2">👤 {agent.name}</div>
    <div class="prose prose-sm prose-invert text-gray-300">
{res}
    </div>
</div>
"""
            # NOTE: If we yield HTML directly as 'token', the frontend accumulating markdown might act weird
            # if it expects pure markdown.
            # However, standard Markdown parsers handle HTML blocks fine.
            # Let's try to stick to Markdown for safety but use quoted blocks.
            
            # 使用 HTML details/summary 实现折叠效果
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
            # 为了内容完整性，debate_content 累加 HTML
            debate_content += section_html
            
            # Stream the agent's output
            yield json.dumps({"type": "token", "content": section_html})
            agent_results.append(f"【{agent.name}意见】:\n{res}")

        # 3. Round 2: CIO Decision
        yield json.dumps({"type": "step", "content": "🤔 首席投资官 (CIO) 正在汇总专家意见..."})
        yield json.dumps({"type": "progress", "value": 85, "message": "首席投资官 (CIO) 正在制定最终决策..."})
        
        cio_context = f"""
{context}

以下是各位专家的意见：
{''.join(agent_results)}

请根据以上信息，进行最终总结和决策。
"""
        cio_result = await self.cio.analyze(cio_context, self.api_config)
        
        yield json.dumps({"type": "progress", "value": 95, "message": "正在生成最终报告..."})
        yield json.dumps({"type": "step", "content": "✍️ CIO 正在签署最终裁决书..."})

        # --- CIO Simluated Streaming ---
        cio_header = "\n\n### 🎖️ 首席投资官 (CIO) 最终裁决\n\n"
        yield json.dumps({"type": "token", "content": cio_header})
        
        # 将结果按 chunk 切分，每隔一小段时间 yield 一次
        chunk_size = 8 # 每次输出8个字符
        for i in range(0, len(cio_result), chunk_size):
            chunk = cio_result[i:i+chunk_size]
            yield json.dumps({"type": "token", "content": chunk})
            await asyncio.sleep(0.01) # 极短的延迟模拟打字感
            
        cio_section = cio_header + cio_result + "\n\n"
        
        # Final formatting
        full_report = debate_content + cio_section
        
        yield json.dumps({"type": "progress", "value": 100, "message": "分析完成"})
        yield json.dumps({"type": "final_html", "content": full_report})
        yield json.dumps({"type": "complete", "content": "Done"})
