#!/usr/bin/env python3
import json, os, sys, urllib.request, urllib.error
BASE='https://paper-api.alpaca.markets'
key=os.environ.get('ALPACA_API_KEY','').strip()
secret=os.environ.get('ALPACA_API_SECRET','').strip()
if not key or not secret:
    print('Set ALPACA_API_KEY and ALPACA_API_SECRET.'); sys.exit(2)
headers={'APCA-API-KEY-ID':key,'APCA-API-SECRET-KEY':secret,'Accept':'application/json'}
checks=[('/v2/account','account'),('/v2/positions','positions'),('/v2/orders?status=all&limit=10','orders'),('/v2/assets?status=active&asset_class=us_equity','assets')]
failed=False
for path,name in checks:
    try:
        req=urllib.request.Request(BASE+path,headers=headers)
        with urllib.request.urlopen(req,timeout=20) as r:
            payload=json.loads(r.read().decode('utf-8'))
            count=len(payload) if isinstance(payload,list) else 1
            print(f'PASS {name}: HTTP {r.status} objects={count}')
    except Exception as e:
        failed=True; print(f'FAIL {name}: {type(e).__name__}: {e}')
sys.exit(1 if failed else 0)
