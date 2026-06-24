import json, os, sys
d = 'eval/results_bench/ours'
if not os.path.isdir(d):
    print("no ours results")
    sys.exit(0)
recs = []
for td in os.listdir(d):
    td_path = os.path.join(d, td)
    rec_path = os.path.join(td_path, 'record.json')
    if os.path.isdir(td_path) and os.path.exists(rec_path):
        r = json.load(open(rec_path, encoding='utf-8'))
        recs.append(r)
print(f"Total records: {len(recs)}")
for r in sorted(recs, key=lambda x: int(x['task_id']) if x['task_id'].isdigit() else 0):
    fid = r['scores']['data_fidelity']
    rounds = r.get('rounds_used', '?')
    vf = r['scores'].get('visual_form', '?')
    sc = r['scores'].get('series_cohesion', '?')
    print(f"  {r['task_id']:>12s}: exec={str(r['exec_pass']):5s} fid={fid:.2f} vf={vf} sc={sc} rounds={rounds}")
