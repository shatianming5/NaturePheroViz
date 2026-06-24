import json
from pathlib import Path
d = Path('eval/results_bench/lida')
for rj in sorted(d.glob('*/record.json'))[-3:]:
    r = json.loads(rj.read_text())
    notes = r.get('notes','')
    # Truncate long notes
    if len(notes) > 200:
        notes = notes[:200] + "..."
    print(f"{rj.parent.name}: pass={r.get('exec_pass')}, df={r.get('scores',{}).get('data_fidelity')}")
    print(f"  notes={notes}")
