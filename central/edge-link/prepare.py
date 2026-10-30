from pathlib import Path
from datetime import datetime, timedelta, timezone
import ipaddress, json, urllib.request, shutil
from cryptography import x509
from cryptography.x509.oid import NameOID, ExtendedKeyUsageOID
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa

root=Path(__file__).resolve().parent
central=Path(r'C:\Users\maiqo\OneDrive\Escritorio\saad-campus_evr2\saad_campus\central')
tls=root/'tls'
bundle=root/'edge-01-connection'
if tls.exists() or bundle.exists():
    raise SystemExit('Certificates already exist; refusing to replace credentials.')
tls.mkdir()
bundle.mkdir()
now=datetime.now(timezone.utc)
def key(): return rsa.generate_private_key(public_exponent=65537,key_size=3072)
def name(cn): return x509.Name([x509.NameAttribute(NameOID.COMMON_NAME,cn)])
ca_key=key()
ca_name=name('SAAD Campus Development CA')
def builder(subject,pub,days):
    return x509.CertificateBuilder().subject_name(subject).issuer_name(ca_name).public_key(pub).serial_number(x509.random_serial_number()).not_valid_before(now-timedelta(minutes=10)).not_valid_after(now+timedelta(days=days))
ca=builder(ca_name,ca_key.public_key(),365).add_extension(x509.BasicConstraints(ca=True,path_length=0),True).add_extension(x509.KeyUsage(False,False,False,False,False,True,True,False,False),True).add_extension(x509.SubjectKeyIdentifier.from_public_key(ca_key.public_key()),False).sign(ca_key,hashes.SHA256())
def write_pair(folder,stem,private,cert):
    (folder/(stem+'.key')).write_bytes(private.private_bytes(serialization.Encoding.PEM,serialization.PrivateFormat.PKCS8,serialization.NoEncryption()))
    (folder/(stem+'.crt')).write_bytes(cert.public_bytes(serialization.Encoding.PEM))
write_pair(tls,'ca',ca_key,ca)
for stem,cn,usage,folder in [('server','saad-central',ExtendedKeyUsageOID.SERVER_AUTH,tls),('client','edge-01',ExtendedKeyUsageOID.CLIENT_AUTH,bundle)]:
    private=key()
    cert=builder(name(cn),private.public_key(),90).add_extension(x509.BasicConstraints(ca=False,path_length=None),True).add_extension(x509.ExtendedKeyUsage([usage]),False).add_extension(x509.KeyUsage(True,False,True,False,False,False,False,False,False),True).add_extension(x509.AuthorityKeyIdentifier.from_issuer_public_key(ca_key.public_key()),False)
    if stem=='server': cert=cert.add_extension(x509.SubjectAlternativeName([x509.IPAddress(ipaddress.ip_address('172.20.10.6'))]),False)
    write_pair(folder,stem,private,cert.sign(ca_key,hashes.SHA256()))
shutil.copyfile(tls/'ca.crt',bundle/'ca.crt')
env=dict(line.split('=',1) for line in (central/'.env').read_text().splitlines() if '=' in line)
def post(path,body,token=None):
    headers={'Content-Type':'application/json'}
    if token: headers['Authorization']='Bearer '+token
    req=urllib.request.Request('http://127.0.0.1:8000'+path,data=json.dumps(body).encode(),headers=headers)
    with urllib.request.urlopen(req,timeout=15) as response: return json.load(response)
token=post('/login',{'username':'admin','password':env['ADMIN_PASSWORD']})['access_token']
node=post('/nodes/edge-01',{},token)
(bundle/'connection.json').write_text(json.dumps({'url':'https://172.20.10.6:8443','node_id':'edge-01','api_key':node['api_key']},indent=2))
shutil.copyfile(root/'sync_once.py',bundle/'sync_once.py')
override=f'''services:
  edge_tls:
    image: nginx:stable-alpine
    ports:
      - "172.20.10.6:8443:8443"
    volumes:
      - "{(root/'nginx.conf').as_posix()}:/etc/nginx/conf.d/default.conf:ro"
      - "{(tls/'server.crt').as_posix()}:/tls/server.crt:ro"
      - "{(tls/'server.key').as_posix()}:/tls/server.key:ro"
      - "{(tls/'ca.crt').as_posix()}:/tls/ca.crt:ro"
    depends_on:
      - api
'''
(central/'compose.edge.yaml').write_text(override)
print('Created TLS certificates (90 days), registered edge-01, and prepared transfer folder.')
