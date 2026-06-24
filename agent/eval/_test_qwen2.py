import os, sys, json
os.environ["LLM_API_BASE"] = "http://1.14.177.180:4141/v1"
os.environ["LLM_API_KEY"] = "sk-intern"
sys.path.insert(0, ".")
from eval.run_benchmark import _load_matplotbench
from eval.baseline_runners import _qwen_generate, QWEN_MODELS

tasks = _load_matplotbench()
print(f"Loaded {len(tasks)} tasks")
t = tasks[0]
print(f"Task 0: id={t['task_id']}, family={t['family']}, goal={t['goal'][:80]}")
print(f"  intent={t.get('intent')}")
print(f"  cols={list(t['data'].columns)}")
print(f"  shape={t['data'].shape}")

code = _qwen_generate(t, QWEN_MODELS["qwen_zeroshot"])
print(f"Result: {code}")
