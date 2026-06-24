import requests, os, json
base = os.getenv("LLM_API_BASE", "http://1.14.177.180:4141/v1")
key = os.getenv("LLM_API_KEY", "sk-intern")

# List available models
r = requests.get(f"{base}/models", headers={"Authorization": f"Bearer {key}"})
data = r.json()
models = [m["id"] for m in data.get("data", [])]
print("Available models:")
for m in sorted(models):
    print(f"  {m}")

# Check if any qwen model exists
qwen_models = [m for m in models if "qwen" in m.lower()]
print(f"\nQwen models found: {qwen_models}")
