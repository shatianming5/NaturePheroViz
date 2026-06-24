import requests, json

KEY = "sk-ws-H.REIIXHX.LiaP.MEYCIQCAxPhVbfwM5uDU6zcsVSURPuAY8YyFqyNsYnQ7cz5z7QIhALzNYcFsSSpCPxsKtGkNpNpILHFFh9e8TBSDClMJXDfq"

# Try multiple Qwen endpoints
endpoints = [
    ("DashScope (阿里百炼)", "https://dashscope.aliyuncs.com/compatible-mode/v1", "qwen-plus"),
    ("DashScope v2", "https://dashscope.aliyuncs.com/api/v1/services/aigc/text-generation/generation", None),
    ("SiliconFlow", "https://api.siliconflow.cn/v1", "Qwen/Qwen2.5-Coder-7B-Instruct"),
    ("OpenRouter", "https://openrouter.ai/api/v1", "qwen/qwen-2.5-7b-instruct"),
    ("Internal Proxy", "http://1.14.177.180:4141/v1", "gpt-5.4"),
    ("Together AI", "https://api.together.xyz/v1", "Qwen/Qwen2.5-Coder-7B-Instruct"),
]

payload_template = {"messages": [{"role": "user", "content": "say hi in one word"}], "max_tokens": 10, "temperature": 0.1}

for name, base, model in endpoints:
    if model:
        payload = {**payload_template, "model": model}
        url = base + "/chat/completions"
    else:
        url = base
        payload = {**payload_template, "model": "qwen-plus"}
    try:
        r = requests.post(url, headers={"Authorization": f"Bearer {KEY}", "Content-Type": "application/json"},
                         json=payload, timeout=15)
        print(f"{name} ({base}): HTTP {r.status_code}")
        print(f"  -> {r.text[:300]}")
    except Exception as e:
        print(f"{name} ({base}): ERROR - {e}")
    print()
