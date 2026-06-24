import requests, os
base = os.getenv("LLM_API_BASE", "http://1.14.177.180:4141/v1").rstrip("/")
key = os.getenv("LLM_API_KEY", "sk-intern")

# Test 1: without response_format
r1 = requests.post(base + "/chat/completions",
    headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
    json={"model": "gpt-5.4", "messages": [{"role":"user","content":"Say hello in one word."}], "temperature":0.2, "max_tokens":20},
    timeout=30)
print(f"Test 1 (no response_format): {r1.status_code}")

# Test 2: with response_format json_object
r2 = requests.post(base + "/chat/completions",
    headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
    json={"model": "gpt-5.4", "messages": [{"role":"user","content":'Say "hello" as JSON: {"word": "hello"}'}], "temperature":0.2, "max_tokens":50, "response_format": {"type": "json_object"}},
    timeout=30)
print(f"Test 2 (json_object): {r2.status_code}")
if r2.status_code == 502:
    print(f"  Response: {r2.text[:200]}")
