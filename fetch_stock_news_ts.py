import tushare as ts
import pandas as pd
import json
import os
from datetime import datetime, timedelta

def get_tushare_token():
    """
    尝试从 config.json 获取 Token，如果失败则返回 None
    """
    try:
        config_path = os.path.join(os.path.dirname(__file__), 'config.json')
        if os.path.exists(config_path):
            with open(config_path, 'r', encoding='utf-8') as f:
                config = json.load(f)
                return config.get('data_source', {}).get('tushare_token')
    except Exception as e:
        print(f"读取配置失败: {e}")
    return None

def main():
    # 1. 设置 Token
    # 如果 config.json 中有配置，直接读取
    token = get_tushare_token()
    
    # 如果没有配置，请在此处手动填入你的 Token
    if not token or token == "your_token":
        # token = '在此处粘贴你的Tushare Token' 
        print("未检测到有效的 Tushare Token。请在 config.json 中配置或在脚本中手动设置。")
        return

    print(f"当前使用的 Token: {token[:6]}******")

    try:
        # 2. 初始化 Pro API
        ts.set_token(token)
        pro = ts.pro_api()

        # 3. 设定查询参数
        stock_code = '600519.SH'  # 贵州茅台
        start_date = (datetime.now() - timedelta(days=30)).strftime('%Y%m%d') # 最近30天
        end_date = datetime.now().strftime('%Y%m%d')

        print(f"\n正在获取股票 {stock_code} 的新闻资讯 ({start_date} - {end_date})...")

        # 4. 获取新闻快讯
        # 注意: pro.news 接口可能需要积分权限，或者使用 pro.cctv_news, pro.sina_news 等
        # 这里使用用户请求的 pro.news
        news = pro.news(src='sina', start_date=start_date, end_date=end_date, ts_code=stock_code)
        
        # 如果指定股票没有特定新闻，尝试不加 ts_code 参数获取通用财经新闻（以此演示接口可用性）
        if news is None or news.empty:
            print(f"未找到 {stock_code} 的直接关联新闻，尝试获取最近的通用财经快讯...")
            news = pro.news(src='sina', start_date=start_date, end_date=end_date) # 去掉 ts_code 限制

        if news is not None and not news.empty:
            print(f"\n✅ 成功获取到 {len(news)} 条新闻:")
            print("-" * 50)
            
            # 仅显示前 10 条
            for index, row in news.head(10).iterrows():
                title = row.get('title', '无标题')
                content = row.get('content', '无内容')
                date = row.get('datetime', '未知时间')
                
                print(f"[{date}] {title}")
                # 简单截断内容以方便显示
                if len(content) > 100:
                    print(f"内容: {content[:100]}...")
                else:
                    print(f"内容: {content}")
                print("-" * 50)
        else:
            print("⚠️ 未获取到任何新闻数据。可能原因：")
            print("1. 该时间段内无新闻")
            print("2. 权限不足 (pro.news 接口通常需要较多积分)")
            print("3. 网络连接问题")

    except Exception as e:
        print(f"❌ 运行出错: {e}")
        print("\n常见问题:")
        print("- 权限不足: 检查 Tushare 积分是否满足 pro.news 接口要求")
        print("- Token 错误: 请检查 Token 是否正确")

if __name__ == "__main__":
    main()
