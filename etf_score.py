"""
ETF Long-term Holding Score Module
宽基ETF长期持有专用评分系统

设计理念：
1. 不惧回调 - 下跌是加仓机会
2. 只看大趋势 - 关注MA60牛熊线，忽略短期MA20波动
3. 逆向思维 - RSI超卖不是风险，而是机会
4. 降低换手 - 过滤短期噪音，避免频繁操作

与个股评分的核心差异：
- 低分 = 加仓机会，而非卖出信号
- 超卖时加分（逆向逻辑）
- 取消量价分析（ETF量能意义有限）
"""
from typing import Dict, Any, Tuple, List


def calculate_etf_score(metrics: Dict[str, Any]) -> Tuple[int, str, List[Tuple[str, int, int]], List[str]]:
    """
    ETF长期持有专用评分系统 (0-100分)
    
    评分维度：
    - 大趋势健康度 (35分): MA60牛熊线关系（核心指标）
    - 估值机会 (30分): 超卖=加仓机会（逆向逻辑）
    - 趋势动量 (20分): MACD长期趋势判断
    - 波动风险 (15分): ATR波动率控制
    
    Returns:
        (总分, 评级, 各维度得分列表, 详细说明列表)
    """
    scores = []
    details = []
    
    # === 大趋势健康度 (35分) ===
    trend_score = 0
    
    close = metrics.get('close', 0)
    ma60 = metrics.get('ma60', 0)
    ma20 = metrics.get('ma20', 0)
    
    # 价格与MA60关系 (20分) - 核心：看牛熊线
    if ma60 > 0:
        if close > ma60:
            trend_score += 20
            details.append("✅ 价格在MA60(牛熊线)上方 → 牛市格局 (+20)")
        elif close > ma60 * 0.95:
            trend_score += 15
            details.append("⚠️ 价格在MA60下方5%以内 → 技术性回调 (+15)")
        elif close > ma60 * 0.90:
            trend_score += 10
            details.append("🟡 价格跌破MA60较多 → 进入调整区（可能是加仓机会）(+10)")
        else:
            trend_score += 5
            details.append("🔴 价格深度跌破MA60 → 深度调整（定投机会区）(+5)")
    else:
        trend_score += 10
        details.append("⚠️ MA60数据不足 (+10)")
    
    # MA20与MA60关系 (15分) - 中期趋势判断
    if ma60 > 0 and ma20 > 0:
        if ma20 > ma60:
            trend_score += 15
            details.append("✅ MA20 > MA60 → 中期趋势向上 (+15)")
        elif ma20 > ma60 * 0.97:
            trend_score += 10
            details.append("🟡 均线粘合 → 方向待定 (+10)")
        else:
            trend_score += 5
            details.append("⚠️ MA20 < MA60 → 中期走弱（但可能是底部区域）(+5)")
    else:
        trend_score += 8
        details.append("⚠️ 均线数据不足 (+8)")
    
    scores.append(('大趋势健康度', trend_score, 35))
    
    # === 估值机会 (30分) - 逆向逻辑 ===
    opportunity_score = 0
    
    # RSI评分 (15分) - 超卖=机会
    rsi = metrics.get('rsi', 50)
    if rsi < 25:
        opportunity_score += 15
        details.append(f"🟢 RSI={rsi:.1f} 极度超卖 → 绝佳定投机会 (+15)")
    elif rsi < 35:
        opportunity_score += 12
        details.append(f"🟢 RSI={rsi:.1f} 超卖 → 好的加仓点 (+12)")
    elif rsi <= 65:
        opportunity_score += 10
        details.append(f"✅ RSI={rsi:.1f} 正常区间 → 持有 (+10)")
    elif rsi <= 75:
        opportunity_score += 6
        details.append(f"⚠️ RSI={rsi:.1f} 偏高 → 暂停定投 (+6)")
    else:
        opportunity_score += 0
        details.append(f"🔴 RSI={rsi:.1f} 过热 → 可考虑部分止盈 (+0)")
    
    # 布林带位置 (15分) - 下轨=机会
    boll_position = metrics.get('boll_position', 50)
    if boll_position < 15:
        opportunity_score += 15
        details.append(f"🟢 布林带位置{boll_position:.1f}% → 触及下轨，加仓信号 (+15)")
    elif boll_position < 30:
        opportunity_score += 12
        details.append(f"🟢 布林带位置{boll_position:.1f}% → 下轨附近，可加仓 (+12)")
    elif boll_position <= 70:
        opportunity_score += 10
        details.append(f"✅ 布林带位置{boll_position:.1f}% → 中轨区间，正常持有 (+10)")
    elif boll_position <= 85:
        opportunity_score += 5
        details.append(f"⚠️ 布林带位置{boll_position:.1f}% → 上轨附近，谨慎 (+5)")
    else:
        opportunity_score += 0
        details.append(f"🔴 布林带位置{boll_position:.1f}% → 极度超买 (+0)")
    
    scores.append(('估值机会', opportunity_score, 30))
    
    # === 趋势动量 (20分) ===
    momentum_score = 0
    
    macd_hist = metrics.get('macd_hist', 0)
    macd_dif = metrics.get('macd_dif', 0)
    macd_dea = metrics.get('macd_dea', 0)
    
    # MACD柱方向 (10分)
    if macd_hist > 0:
        momentum_score += 8
        details.append("✅ MACD红柱 → 动量为正 (+8)")
    elif macd_hist > -0.1:  # 接近零轴
        momentum_score += 5
        details.append("🟡 MACD绿柱但接近零轴 → 可能见底 (+5)")
    else:
        momentum_score += 2
        details.append("⚠️ MACD绿柱 → 下跌动量（但长期投资可忽略）(+2)")
    
    # DIF与DEA关系 (10分)
    if macd_dif > macd_dea:
        momentum_score += 10
        details.append("✅ MACD金叉状态 (+10)")
    elif macd_dea != 0 and macd_dif > macd_dea * 0.95:
        momentum_score += 6
        details.append("🟡 接近MACD金叉 (+6)")
    else:
        momentum_score += 3
        details.append("⚠️ MACD死叉状态（长期投资可忽略）(+3)")
    
    scores.append(('趋势动量', momentum_score, 20))
    
    # === 波动风险 (15分) ===
    volatility_score = 0
    
    atr_pct = metrics.get('atr_pct', 2)
    
    if atr_pct < 1.5:
        volatility_score += 15
        details.append(f"✅ ATR波动率{atr_pct:.2f}% → 低波动，适合持有 (+15)")
    elif atr_pct < 2.5:
        volatility_score += 12
        details.append(f"✅ ATR波动率{atr_pct:.2f}% → 正常波动 (+12)")
    elif atr_pct < 4:
        volatility_score += 8
        details.append(f"⚠️ ATR波动率{atr_pct:.2f}% → 波动增大，正常调整 (+8)")
    else:
        volatility_score += 4
        details.append(f"🟡 ATR波动率{atr_pct:.2f}% → 高波动（市场恐慌，可能是机会）(+4)")
    
    scores.append(('波动风险', volatility_score, 15))
    
    # === 计算总分和评级 ===
    total_score = sum(s[1] for s in scores)
    
    # ETF专用评级标准（与个股不同）
    if total_score >= 80:
        rating = "健康持仓 🟢🟢🟢"
    elif total_score >= 65:
        rating = "稳健 🟢🟢"
    elif total_score >= 50:
        rating = "观望 🟡"
    elif total_score >= 35:
        rating = "机会区 🟠"
    else:
        rating = "深度机会 🔴"
    
    return total_score, rating, scores, details


def get_etf_operation_suggestion(total_score: int, metrics: Dict[str, Any]) -> str:
    """
    根据ETF评分给出操作建议
    
    核心逻辑：低分不是卖出信号，而是加仓机会
    """
    rsi = metrics.get('rsi', 50)
    close = metrics.get('close', 0)
    ma60 = metrics.get('ma60', 0)
    boll_position = metrics.get('boll_position', 50)
    
    if total_score >= 80:
        return "【持有】当前处于健康状态，继续持有，可正常定投"
    elif total_score >= 65:
        return "【持有+定投】趋势稳健，适合继续定投积累份额"
    elif total_score >= 50:
        if rsi < 40 or boll_position < 30:
            return "【观望/小额加仓】虽然评分中性，但超卖信号出现，可考虑小额加仓"
        else:
            return "【观望】暂停定投，保持现有仓位，等待更好机会"
    elif total_score >= 35:
        if close < ma60 * 0.95:
            return "【分批加仓】进入机会区域，建议分2-3批逢低加仓"
        else:
            return "【观察】接近机会区，但跌幅不够深，继续观察"
    else:
        return "【积极加仓】深度调整区域，是长期投资者难得的加仓良机，建议分批买入"


def format_etf_score_section(metrics: Dict[str, Any]) -> str:
    """
    格式化ETF评分部分的Markdown输出
    """
    score = metrics.get('composite_score', 'N/A')
    rating = metrics.get('rating', '未知')
    score_breakdown = metrics.get('score_breakdown', [])
    score_details = metrics.get('score_details', [])
    
    section = f"\n### 📊 ETF长期持有评分：{score}分 - {rating}\n\n"
    
    # 操作建议
    suggestion = get_etf_operation_suggestion(score, metrics)
    section += f"**💡 操作建议：{suggestion}**\n\n"
    
    # 评分明细
    if score_breakdown:
        section += "**评分明细：**\n"
        for name, got, total in score_breakdown:
            # 计算填充进度条
            filled = int(got / total * 10)
            bar = "█" * filled + "░" * (10 - filled)
            section += f"- {name}：[{bar}] {got}/{total}分\n"
        section += "\n"
    
    # 详细说明
    if score_details:
        section += "**详细分析：**\n"
        for detail in score_details:
            section += f"- {detail}\n"
    
    # ETF特别提醒
    section += "\n> ⚠️ **ETF投资提醒**：此评分系统专为长期持有设计。低分代表加仓机会，而非卖出信号。\n"
    
    return section


def apply_etf_score(metrics: Dict[str, Any]) -> Dict[str, Any]:
    """
    将ETF评分应用到指标数据中
    替换原有的个股评分
    
    Args:
        metrics: 由 indicator_calc.get_latest_metrics 返回的指标字典
        
    Returns:
        更新了评分的指标字典
    """
    # 计算ETF专用评分
    total_score, rating, scores, details = calculate_etf_score(metrics)
    
    # 替换原有评分
    metrics['composite_score'] = total_score
    metrics['rating'] = rating
    metrics['score_breakdown'] = scores
    metrics['score_details'] = details
    metrics['score_type'] = 'etf'  # 标记评分类型
    
    # 添加ETF专用操作建议
    metrics['operation_suggestion'] = get_etf_operation_suggestion(total_score, metrics)
    
    return metrics