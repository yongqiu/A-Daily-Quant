"""
测试新的 Google Gen AI SDK
"""
import json
import os

try:
    from google import genai
    from google.genai import types
    print("✅ google-genai SDK 已安装")
except ImportError as e:
    print(f"❌ 导入失败: {e}")
    exit(1)

# 加载配置
with open('config.json', 'r', encoding='utf-8') as f:
    config = json.load(f)

# 检查是否配置了 Gemini
if 'api_gemini' in config:
    gemini_config = config['api_gemini']
    print(f"\n📋 Gemini 配置:")
    print(f"  - Project ID: {gemini_config.get('project_id')}")
    print(f"  - Location: {gemini_config.get('location')}")
    print(f"  - Model: {gemini_config.get('model')}")
    print(f"  - Credentials: {gemini_config.get('credentials_path')}")
    
    try:
        # 设置凭证文件
        credentials_path = gemini_config.get('credentials_path')
        if credentials_path and os.path.exists(credentials_path):
            os.environ['GOOGLE_APPLICATION_CREDENTIALS'] = credentials_path
            print(f"\n🔑 使用服务账号: {credentials_path}")
        else:
            print(f"\n⚠️  凭证文件不存在: {credentials_path}")
        
        # 创建客户端（使用新的 API）
        client = genai.Client(
            vertexai=True,
            project=gemini_config['project_id'],
            location=gemini_config['location']
        )
        print("✅ Gemini 客户端创建成功")
        
        # 测试简单的生成
        print("\n🧪 测试生成内容...")
        response = client.models.generate_content(
            model=gemini_config['model'],
            contents="用一句话介绍你自己",
            config=types.GenerateContentConfig(
                temperature=0.3,
                max_output_tokens=100,
            )
        )
        
        print(f"\n📝 AI 回复: {response.text}")
        print("\n✅ 测试成功！新的 API 工作正常，没有弃用警告。")
        
    except Exception as e:
        print(f"\n❌ 测试失败: {e}")
        print("\n💡 提示：")
        print("   1. 检查凭证文件路径是否正确")
        print("   2. 检查凭证文件是否有效")
        print("   3. 或者运行: gcloud auth application-default login")
else:
    print("\n⚠️  config.json 中未找到 'api_gemini' 配置")
