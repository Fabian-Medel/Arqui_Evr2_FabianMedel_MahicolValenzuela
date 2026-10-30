from pathlib import Path
import sys, ssl, json, urllib.request
from getpass import getpass
from datetime import datetime, timezone

HERE=Path(__file__).resolve().parent
PROJECT=HERE.parent
sys.path.insert(0,str(PROJECT))
from edge_db import connect, DB_PATH

def main():
    config=json.loads((HERE/'connection.json').read_text())
    ctx=ssl.create_default_context(cafile=str(HERE/'ca.crt'))
    ctx.load_cert_chain(str(HERE/'client.crt'),str(HERE/'client.key'))
    # Ignore ambient HTTP proxy settings for the private LAN connection.
    opener=urllib.request.build_opener(urllib.request.ProxyHandler({}),urllib.request.HTTPSHandler(context=ctx))
    def request(path,body=None):
        headers={'X-Node-Id':config['node_id'],'X-Node-Key':config['api_key'],'Content-Type':'application/json'}
        req=urllib.request.Request(config['url']+path,headers=headers,data=None if body is None else json.dumps(body).encode())
        with opener.open(req,timeout=15) as response: return json.load(response)
    snapshot=request('/edge/policies')
    if snapshot.get('replace_snapshot') is not True: raise ValueError('Invalid policy snapshot')
    policies=snapshot['permissions']
    if not isinstance(policies,list): raise ValueError('Invalid permissions list')
    for p in policies:
        if not isinstance(p.get('student_id'),str) or not isinstance(p.get('zone'),str) or type(p.get('enabled')) is not bool:
            raise ValueError('Invalid policy entry')
    print('HTTPS/mTLS: OK. Central authentication: OK.')
    if not DB_PATH.is_file(): raise RuntimeError('Encrypted database not found')
    db=connect(getpass('Clave de la base cifrada: '))
    try:
        with db:
            db.execute('DELETE FROM permissions')
            db.executemany('INSERT INTO permissions(student_id,zone,enabled) VALUES (?,?,?)',[(p['student_id'],p['zone'],int(p['enabled'])) for p in policies])
            db.execute('INSERT OR REPLACE INTO sync_state(name,value) VALUES (?,?)',('last_policy_sync',datetime.now(timezone.utc).isoformat()))
        print('Permisos sincronizados:',len(policies))
        permission=db.execute('SELECT enabled FROM permissions WHERE student_id=? AND zone=?',('ALUMNO-001','ENTRADA-PRINCIPAL')).fetchone()
        print('ALUMNO-001 / ENTRADA-PRINCIPAL:', 'HABILITADO' if permission and permission[0] else 'SIN PERMISO')
        pending=db.execute('SELECT id,student_id,zone,allowed,occurred_at FROM pending_events WHERE synced_at IS NULL ORDER BY occurred_at').fetchall()
        sent=0
        for row in pending:
            event=dict(zip(['id','student_id','zone','allowed','occurred_at'],row))
            event['allowed']=bool(event['allowed'])
            receipt=request('/edge/events',event)
            if receipt.get('ok') is not True: raise RuntimeError('Central did not acknowledge event')
            with db:
                db.execute('UPDATE pending_events SET synced_at=? WHERE id=?',(datetime.now(timezone.utc).isoformat(),event['id']))
            sent+=1
        print('Eventos enviados:',sent)
    finally: db.close()

if __name__=='__main__':
    try: main()
    except Exception as error:
        print('Sincronizacion no completada:',type(error).__name__,str(error))
        sys.exit(1)
