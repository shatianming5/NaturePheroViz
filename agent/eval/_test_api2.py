import requests, os, json, traceback

base = "http://1.14.177.180:4141/v1"
key = "sk-intern"

payload = {
    "model": "gpt-5.4",
    "messages": [{"role": "user", "content": 'Return ONLY strict JSON: {"code": "print(1)"}'}],
    "temperature": 0.2,
    "max_tokens": 400,
    "response_format": {"type": "json_object"},
}

print("Sending request...")
try:
    r = requests.post(
        base + "/chat/completions",
        headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
        json=payload,
        timeout=(10, 60),
    )
    print(f"Status: {r.status_code}")
    print(f"Response: {r.text[:500]}")
except Exception as e:
    traceback.print_exc()
