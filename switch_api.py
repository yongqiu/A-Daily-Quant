#!/usr/bin/env python3
"""
快速切换 LLM API 提供商
"""
import json
import sys

CONFIG_FILE = 'config.json'

def load_config():
    with open(CONFIG_FILE, 'r', encoding='utf-8') as f:
        return json.load(f)

def save_config(config):
    with open(CONFIG_FILE, 'w', encoding='utf-8') as f:
        json.dump(config, f, indent=2, ensure_ascii=False)

def switch_provider(provider):
    config = load_config()
    
    # 检查是否有对应的配置
    config_key = f"api_{provider}"
    if config_key not in config and provider != 'openai':
        print(f"❌ 错误：未找到 '{config_key}' 配置")
        print(f"\n可用的配置：")
        for key in config.keys():
            if key.startswith('api_'):
                print(f"  - {key.replace('api_', '')}")
        return False
    
    # 更新 provider
    old_provider = config['api'].get('provider', 'unknown')
    config['api']['provider'] = provider
    
    # 保存配置
    save_config(config)
    
    print(f"✅ 成功切换 LLM 提供商")
    print(f"   从: {old_provider}")
    print(f"   到: {provider}")
    print(f"\n配置详情：")
    
    if config_key in config:
        api_config = config[config_key]
        print(f"  - 配置来源: {config_key}")
        print(f"  - 模型: {api_config.get('model', 'N/A')}")
        if 'base_url' in api_config:
            print(f"  - API 地址: {api_config['base_url']}")
        if 'project_id' in api_config:
            print(f"  - 项目 ID: {api_config['project_id']}")
    else:
        print(f"  - 配置来源: api (默认)")
    
    print(f"\n现在可以运行: ./run.sh")
    return True

def show_current():
    config = load_config()
    provider = config['api'].get('provider', 'unknown')
    
    print(f"📊 当前 LLM 提供商: {provider}")
    print(f"\n可用的配置：")
    
    for key in sorted(config.keys()):
        if key.startswith('api_'):
            provider_name = key.replace('api_', '')
            api_config = config[key]
            model = api_config.get('model', 'N/A')
            status = "✅ 当前" if provider_name == provider else "  "
            print(f"{status} {provider_name:12} - {model}")

def main():
    if len(sys.argv) < 2:
        print("🔄 LLM API 提供商切换工具")
        print("\n用法:")
        print("  python switch_api.py <provider>")
        print("  python switch_api.py status")
        print("\n示例:")
        print("  python switch_api.py deepseek   # 切换到 DeepSeek")
        print("  python switch_api.py gemini     # 切换到 Gemini")
        print("  python switch_api.py status     # 查看当前配置")
        print()
        show_current()
        return
    
    command = sys.argv[1].lower()
    
    if command == 'status':
        show_current()
    else:
        switch_provider(command)

if __name__ == '__main__':
    main()
