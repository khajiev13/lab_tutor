import json

with open('backend/app/modules/marketdemandanalyst/notebooks/market_demand_agent.ipynb') as f:
    nb = json.load(f)

# Check cell 11 - the first chat()
cell = nb['cells'][11]
print(f"Cell 11 has {len(cell.get('outputs', []))} outputs\n")

for i, out in enumerate(cell.get('outputs', [])):
    otype = out.get('output_type', '?')
    if 'text' in out:
        text = ''.join(out['text'])
        print(f"[{i}] {otype} (text): {text[:300]}")
    elif 'data' in out:
        for mime in out['data']:
            t = ''.join(out['data'][mime]) if isinstance(out['data'][mime], list) else str(out['data'][mime])
            print(f"[{i}] {otype} ({mime}): {t[:300]}")
    elif 'ename' in out:
        print(f"[{i}] ERROR: {out['ename']}: {out['evalue']}")
    print()
