"""Quick test: can LIDA generate useful matplotlib code at all?"""
import os, json, sys
os.environ["LLM_API_BASE"] = "http://1.14.177.180:4141/v1"
os.environ["LLM_API_KEY"] = "sk-intern"
os.environ["OPENAI_API_KEY"] = "sk-intern"
os.environ["OPENAI_BASE_URL"] = "http://1.14.177.180:4141/v1"
sys.path.insert(0, ".")

from lida import Manager, TextGenerationConfig, llm
import pandas as pd
from pathlib import Path

# Simple test data
df = pd.DataFrame({"month": ["Jan","Feb","Mar"], "sales": [100,200,150]})
csv_path = Path("eval/_lida_test.csv")
df.to_csv(csv_path, index=False)

lida_cfg = TextGenerationConfig(n=1, temperature=0.2, model="gpt-5.4")
lida_manager = Manager(text_gen=llm("openai"))

print("=== Summarize ===")
summary = lida_manager.summarize(str(csv_path), textgen_config=lida_cfg)
print(f"Summary: {str(summary)[:300]}")

print("\n=== Visualize ===")
charts = lida_manager.visualize(summary=summary, goal="Show monthly sales trend", textgen_config=lida_cfg)
print(f"Charts count: {len(charts)}")
if charts:
    chart = charts[0]
    print(f"Status: {chart.status}")
    print(f"Code (first 500 chars):")
    print(chart.code[:500] if chart.code else "NO CODE")
