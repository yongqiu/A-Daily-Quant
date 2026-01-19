import requests
import json

url = "http://127.0.0.1:8100/api/holdings"

# 模拟前端发送的数据 (包含 isEdit)
data = {
    "symbol": "600519",
    "name": "贵州茅台",
    "asset_type": "stock",
    "cost_price": 1635.0,
    "position_size": 0,
    "isEdit": False
}

print(f"Sending data: {json.dumps(data, indent=2)}")

headers = {
    "Content-Type": "application/json"
}

try:
    response = requests.post(url, json=data, headers=headers)
    print(f"Status Code: {response.status_code}")
    print(f"Response Body: {response.text}")
except Exception as e:
    print(f"Error: {e}")