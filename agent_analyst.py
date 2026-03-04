"""
Multi-Agent Analyst Module
Orchestrates a debate between multiple AI agents with different personas to analyze a stock.
统一使用 llm_analyst.generate_analysis 作为 LLM 调用入口。
"""

import asyncio
import json
import logging
from typing import Dict, Any, List, AsyncGenerator
from datetime import datetime

# 导入统一的分析入口
from llm_analyst import generate_analysis

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class StockAnalystAgent:
    """
    代表一个专业分析师 Agent。
    通过 analysis_type（即 slug）调用 generate_analysis，
    由 llm_analyst.py 中的 create_analysis_prompt + _get_system_instruction 统一构建 prompt。
    """

    def __init__(self, slug: str, name: str, role: str, description: str):
        self.slug = slug
        self.name = name
        self.role = role
        self.description = description

    async def analyze(
        self,
        context: Dict[str, Any],
        api_config: Dict[str, Any],
        **kwargs,
    ) -> str:
        """
        通过 generate_analysis 统一入口执行分析。
        使用 asyncio.to_thread 将同步调用包装为异步，支持并发执行。
        """
        try:
            result = await asyncio.to_thread(
                generate_analysis,
                context=context,
                api_config=api_config,
                analysis_type=self.slug,  # 如 "agent_technician"
                **kwargs,
            )
            return result
        except Exception as e:
            logger.error(f"Agent {self.name} 分析失败: {e}")
            return f"**{self.name} 分析失败**: {str(e)}"


class MultiAgentSystem:
    def __init__(self, api_config: Dict[str, Any]):
        self.api_config = api_config
        self.agents = []
        self._load_agents()

    def _load_agents(self):
        """从数据库加载 Agent 配置"""
        import database

        # 三位辩论专家
        agent_configs = [
            {
                "slug": "agent_trend_follower",
                "fallback_name": "趋势跟随者 (Trend Follower)",
            },
            {
                "slug": "agent_washout_hunter",
                "fallback_name": "异动分析师 (Washout Hunter)",
            },
            {
                "slug": "agent_fundamentals",
                "fallback_name": "基本面分析师 (Fundamentals)",
            },
        ]

        self.agents = []

        for cfg in agent_configs:
            strategy = database.get_strategy_by_slug(cfg["slug"])
            if strategy:
                self.agents.append(
                    StockAnalystAgent(
                        slug=cfg["slug"],
                        name=strategy["name"],
                        role=strategy["params"].get("role", "Experts"),
                        description=strategy.get("description", ""),
                    )
                )
            else:
                print(
                    f"⚠️ Warning: Agent strategy {cfg['slug']} not found in DB. Using fallback."
                )
                pass

        # 加载 CIO
        cio_slug = "agent_cio"
        strategy = database.get_strategy_by_slug(cio_slug)
        if strategy:
            self.cio = StockAnalystAgent(
                slug=cio_slug,
                name=strategy["name"],
                role=strategy["params"].get("role", "CIO"),
                description=strategy.get("description", ""),
            )
        else:
            print(f"⚠️ Warning: CIO strategy {cio_slug} not found in DB.")

    async def run_debate_stream(
        self,
        context: Dict[str, Any],
        start_progress: int = 30,
    ) -> AsyncGenerator[str, None]:
        """
        运行多智能体辩论并生成 SSE 事件流。
        数据拼装与 prompt 构建已统一下沉到 llm_analyst.py，
        此处只负责调度各 Agent 并合并结果。
        """

        yield json.dumps(
            {
                "type": "progress",
                "value": start_progress,
                "message": "初始化多智能体辩论环境...",
            }
        )
        yield json.dumps({"type": "step", "content": "🔔 辩论组建完毕，准备开始..."})
        yield json.dumps(
            {"type": "token", "content": "\n\n# 🤖 AI 专家团队辩论纪要\n\n"}
        )

        agent_results = []
        tasks = []
        total_agents = len(self.agents)
        current_progress = start_progress + 5
        yield json.dumps(
            {
                "type": "progress",
                "value": current_progress,
                "message": "专家团队开始并行分析...",
            }
        )

        # 并行调用所有辩论专家（各自的 prompt 由 generate_analysis 内部调度）
        for agent in self.agents:
            tasks.append(
                agent.analyze(
                    context,
                    self.api_config,
                )
            )

        results = await asyncio.gather(*tasks)

        debate_content = ""
        progress_range_agents = 45

        for i, res in enumerate(results):
            agent = self.agents[i]
            inc = int(((i + 1) / total_agents) * progress_range_agents)
            progress_pct = current_progress + inc

            yield json.dumps(
                {
                    "type": "progress",
                    "value": progress_pct,
                    "message": f"{agent.name} 完成分析",
                }
            )
            yield json.dumps(
                {"type": "step", "content": f"✅ {agent.name} 提交了分析报告"}
            )

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
{res.replace(chr(10), "<br/>")}
    </div>
</details>
<div class="h-2"></div>
"""
            debate_content += section_html
            yield json.dumps({"type": "token", "content": section_html})
            agent_results.append(f"【{agent.name}意见】:\n{res}")

        # CIO 裁决：传递 agent_results 给 generate_analysis
        yield json.dumps(
            {"type": "step", "content": "🤔 首席投资官 (CIO) 正在汇总专家意见..."}
        )
        yield json.dumps(
            {
                "type": "progress",
                "value": 85,
                "message": "首席投资官 (CIO) 正在制定最终决策...",
            }
        )

        cio_result = await self.cio.analyze(
            context,
            self.api_config,
            agent_results=agent_results,
        )

        yield json.dumps(
            {"type": "progress", "value": 95, "message": "正在生成最终报告..."}
        )
        yield json.dumps({"type": "step", "content": "✍️ CIO 正在签署最终裁决书..."})

        cio_header = "\n\n### 🎖️ 首席投资官 (CIO) 最终裁决\n\n"
        yield json.dumps({"type": "token", "content": cio_header})

        # 逐块流式输出 CIO 结果
        chunk_size = 8
        for i in range(0, len(cio_result), chunk_size):
            chunk = cio_result[i : i + chunk_size]
            yield json.dumps({"type": "token", "content": chunk})
            await asyncio.sleep(0.01)

        cio_section = cio_header + cio_result + "\n\n"
        full_report = debate_content + cio_section

        yield json.dumps({"type": "progress", "value": 100, "message": "分析完成"})
        yield json.dumps({"type": "final_html", "content": full_report})
        yield json.dumps({"type": "complete", "content": "Done"})
