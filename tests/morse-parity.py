#!/usr/bin/env python3
import json,random,subprocess,sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).parents[1]/'backend'))
from fcc import cw_weight
rng=random.Random(730)
calls=list('ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789')+['AE7Q','KR4GOJ','PARIS',' k1ab ','','K1?','K1/AB','é1a']
calls += [''.join(rng.choices('ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789',k=rng.randrange(1,12))) for _ in range(1000)]
output=subprocess.check_output([sys.argv[1]],input='\n'.join(calls)+'\n',text=True).splitlines()
assert len(output)==len(calls)
for call,result in zip(calls,output):assert json.loads(result)==cw_weight(call),(call,result,cw_weight(call))
print(f'Passed Swift/Python Morse parity for {len(calls)} inputs')
