import json, ssl, urllib.request, urllib.error, sys
from pathlib import Path
p=Path(__file__).resolve().parent/'edge-01-connection'
c=json.loads((p/'connection.json').read_text())
if len(sys.argv) > 1:
    c['url'] = sys.argv[1]
def call(client=True,key=True,path='/edge/policies'):
    ctx=ssl.create_default_context(cafile=str(p/'ca.crt'))
    if client: ctx.load_cert_chain(str(p/'client.crt'),str(p/'client.key'))
    opener=urllib.request.build_opener(urllib.request.ProxyHandler({}),urllib.request.HTTPSHandler(context=ctx))
    headers={'X-Node-Id':'edge-01','X-Node-Key':c['api_key'] if key else 'invalid'}
    return opener.open(urllib.request.Request(c['url']+path,headers=headers),timeout=10)
with call() as response:
    snapshot=json.load(response)
    assert snapshot['replace_snapshot'] is True
    print('PASS HTTPS/mTLS and node authentication.')
    print('ALUMNO-001 permission:',any(x['student_id']=='ALUMNO-001' and x['zone']=='ENTRADA-PRINCIPAL' and x['enabled'] for x in snapshot['permissions']))
for kwargs,label,expected in [({'client':False},'missing certificate',400),({'key':False},'incorrect key',401),({'path':'/dashboard'},'admin route blocked',404)]:
    try:
        with call(**kwargs): pass
    except urllib.error.HTTPError as e:
        assert e.code==expected,(label,e.code)
        print('PASS',label,'rejected:',e.code)
    else: raise AssertionError(label+' was not rejected')
