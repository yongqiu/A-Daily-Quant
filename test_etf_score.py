"""
Test script for ETF scoring system
验证ETF专用评分系统是否正常工作
"""
from etf_score import calculate_etf_score, apply_etf_score, get_etf_operation_suggestion, format_etf_score_section

def test_etf_score():
    """Test with sample metrics data"""
    
    # 模拟一个健康的ETF数据（价格在MA60上方，RSI正常）
    healthy_etf = {
        'close': 1.50,
        'open': 1.48,
        'high': 1.52,
        'low': 1.47,
        'date': '2026-01-08',
        'ma5': 1.48,
        'ma10': 1.45,
        'ma20': 1.42,
        'ma60': 1.35,
        'distance_from_ma20': 5.6,
        'ma_arrangement': '多头排列',
        'rsi': 55,
        'rsi_signal': '中性',
        'kdj_k': 60,
        'kdj_d': 55,
        'kdj_j': 70,
        'kdj_signal': '金叉',
        'kdj_zone': '正常区',
        'macd_dif': 0.02,
        'macd_dea': 0.015,
        'macd_hist': 0.01,
        'macd_signal': '看涨',
        'boll_upper': 1.55,
        'boll_mid': 1.42,
        'boll_lower': 1.29,
        'boll_position': 65,
        'boll_signal': '中轨附近',
        'boll_width': 18,
        'atr': 0.03,
        'atr_pct': 2.0,
        'stop_loss_suggest': 1.44,
        'resistance': 1.55,
        'support': 1.40,
        'distance_to_resistance': 3.3,
        'distance_to_support': 6.7,
        'volume': 1000000,
        'volume_ma': 800000,
        'volume_ratio': 1.25,
        'volume_pattern': '放量上涨',
        'volume_confirmation': '有效',
        'trend_signal': '看涨',
        'price_change_pct': 1.35,
        # 原有个股评分（将被替换）
        'composite_score': 75,
        'rating': '偏多 🟢🟢',
        'score_breakdown': [],
        'score_details': []
    }
    
    # 模拟一个超卖的ETF数据（价格在MA60下方，RSI低）- 这应该是加仓机会
    oversold_etf = {
        'close': 1.20,
        'open': 1.22,
        'high': 1.23,
        'low': 1.18,
        'date': '2026-01-08',
        'ma5': 1.25,
        'ma10': 1.30,
        'ma20': 1.35,
        'ma60': 1.40,
        'distance_from_ma20': -11.1,
        'ma_arrangement': '空头排列',
        'rsi': 25,
        'rsi_signal': '超卖',
        'kdj_k': 15,
        'kdj_d': 20,
        'kdj_j': 5,
        'kdj_signal': '死叉',
        'kdj_zone': '超卖区',
        'macd_dif': -0.03,
        'macd_dea': -0.02,
        'macd_hist': -0.02,
        'macd_signal': '看跌',
        'boll_upper': 1.50,
        'boll_mid': 1.35,
        'boll_lower': 1.20,
        'boll_position': 0,
        'boll_signal': '接近下轨',
        'boll_width': 22,
        'atr': 0.05,
        'atr_pct': 4.2,
        'stop_loss_suggest': 1.10,
        'resistance': 1.35,
        'support': 1.15,
        'distance_to_resistance': 12.5,
        'distance_to_support': 4.2,
        'volume': 1500000,
        'volume_ma': 800000,
        'volume_ratio': 1.87,
        'volume_pattern': '放量下跌',
        'volume_confirmation': '有效',
        'trend_signal': '看跌',
        'price_change_pct': -1.64,
        # 原有个股评分
        'composite_score': 25,
        'rating': '强烈看空 🔴🔴🔴',
        'score_breakdown': [],
        'score_details': []
    }
    
    print("=" * 60)
    print("🧪 测试 ETF 专用评分系统")
    print("=" * 60)
    
    # 测试1: 健康ETF
    print("\n📈 测试1: 健康的ETF (价格>MA60, RSI正常)")
    print("-" * 40)
    
    score, rating, breakdown, details = calculate_etf_score(healthy_etf)
    print(f"评分: {score}分 - {rating}")
    print(f"\n维度得分:")
    for name, got, total in breakdown:
        print(f"  - {name}: {got}/{total}")
    print(f"\n详细分析:")
    for d in details:
        print(f"  {d}")
    
    suggestion = get_etf_operation_suggestion(score, healthy_etf)
    print(f"\n💡 操作建议: {suggestion}")
    
    # 测试2: 超卖ETF (在个股系统中是卖出信号，但在ETF系统中应该是加仓机会)
    print("\n" + "=" * 60)
    print("\n📉 测试2: 超卖的ETF (价格<MA60, RSI<30)")
    print("-" * 40)
    
    score2, rating2, breakdown2, details2 = calculate_etf_score(oversold_etf)
    print(f"评分: {score2}分 - {rating2}")
    print(f"\n维度得分:")
    for name, got, total in breakdown2:
        print(f"  - {name}: {got}/{total}")
    print(f"\n详细分析:")
    for d in details2:
        print(f"  {d}")
    
    suggestion2 = get_etf_operation_suggestion(score2, oversold_etf)
    print(f"\n💡 操作建议: {suggestion2}")
    
    # 测试3: apply_etf_score 函数
    print("\n" + "=" * 60)
    print("\n🔄 测试3: apply_etf_score 函数替换评分")
    print("-" * 40)
    
    print(f"替换前 - 个股评分: {oversold_etf['composite_score']}分, {oversold_etf['rating']}")
    
    updated_metrics = apply_etf_score(oversold_etf.copy())
    
    print(f"替换后 - ETF评分: {updated_metrics['composite_score']}分, {updated_metrics['rating']}")
    print(f"评分类型标记: {updated_metrics.get('score_type')}")
    print(f"操作建议: {updated_metrics.get('operation_suggestion')}")
    
    # 验证逻辑
    print("\n" + "=" * 60)
    print("✅ 验证总结")
    print("=" * 60)
    
    # 对于超卖ETF，ETF评分应该显示"机会"而非"看空"
    if "机会" in rating2 or score2 >= 35:
        print("✅ 超卖ETF被正确识别为'机会区'而非'看空'")
    else:
        print(f"⚠️ 超卖ETF评分可能需要调整: {rating2}")
    
    if "加仓" in suggestion2:
        print("✅ 操作建议正确提示了加仓机会")
    else:
        print(f"⚠️ 操作建议可能需要调整: {suggestion2}")
    
    if updated_metrics.get('score_type') == 'etf':
        print("✅ score_type 标记正确设置为 'etf'")
    else:
        print("⚠️ score_type 标记未正确设置")
    
    print("\n🎉 ETF评分系统测试完成!")

if __name__ == "__main__":
    test_etf_score()