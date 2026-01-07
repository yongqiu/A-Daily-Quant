"""
测试 Gemini 响应是否完整
"""
import json
import os
from google import genai
from google.genai import types

# 加载配置
with open('config.json', 'r', encoding='utf-8') as f:
    config = json.load(f)

gemini_config = config['api_gemini']

# 设置凭证
os.environ['GOOGLE_APPLICATION_CREDENTIALS'] = gemini_config['credentials_path']

# 创建客户端
client = genai.Client(
    vertexai=True,
    project=gemini_config['project_id'],
    location=gemini_config['location']
)

# 测试提示词
test_prompt = """你是一名严格的A股风险控制官。请分析以下股票：

**股票信息：**
- 代码：159369
- 名称：创50ETF
- 当前价格：¥1.34
- 成本价：¥0.82
- 盈亏：63.41%

**技术数据：**
- MA20：¥1.28 | MA60：¥1.19
- 距离MA20：4.69%
- MACD：DIF=0.0234, DEA=0.0189, 柱=0.009
- RSI：62.5 (中性)
- KDJ：K=65.2, D=58.3, J=79.0 (金叉)
- 成交量变化：-15.2%
- 价格变化：1.52%
- 趋势信号：看涨
- MACD信号：看涨

请提供简洁的分析（3-4句话），包括：
1. 当前趋势评估（基于均线位置）
2. 动量分析（基于RSI、KDJ、MACD）
3. 成交量确认情况
4. 明确建议：持有/减仓/等待/谨慎买入
5. 一个关键风险警告

用中文回答，格式清晰，直接可操作。"""

print("🧪 测试 Gemini 响应...")
print(f"📝 提示词长度: {len(test_prompt)} 字符\n")

try:
    response = client.models.generate_content(
        model='gemini-2.5-flash',  # 使用 flash 版本测试
        contents=test_prompt,
        config=types.GenerateContentConfig(
            temperature=0.3,
            max_output_tokens=2048,
        )
    )
    
    print("=" * 60)
    print("📊 响应对象信息:")
    print(f"  - Type: {type(response)}")
    print(f"  - Has text attr: {hasattr(response, 'text')}")
    print(f"  - Has candidates attr: {hasattr(response, 'candidates')}")
    
    if hasattr(response, 'candidates'):
        print(f"  - Candidates count: {len(response.candidates)}")
        if len(response.candidates) > 0:
            candidate = response.candidates[0]
            print(f"  - Candidate type: {type(candidate)}")
            print(f"  - Has finish_reason: {hasattr(candidate, 'finish_reason')}")
            if hasattr(candidate, 'finish_reason'):
                print(f"  - Finish reason: {candidate.finish_reason}")
    
    print("=" * 60)
    
    # 获取文本
    text = response.text
    print(f"\n✅ 响应文本长度: {len(text)} 字符")
    print(f"\n📝 完整响应:\n")
    print(text)
    print("\n" + "=" * 60)
    
    # 检查是否被截断
    if len(text) < 100:
        print("⚠️  警告：响应太短，可能被截断")
    elif not text.endswith(('。', '！', '？', '.', '!', '?')):
        print("⚠️  警告：响应可能未完成（没有结束标点）")
    else:
        print("✅ 响应看起来完整")
        
except Exception as e:
    print(f"❌ 错误: {e}")
    import traceback
    traceback.print_exc()
