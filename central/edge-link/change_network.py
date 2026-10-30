from pathlib import Path
from datetime import datetime,timedelta,timezone
import ipaddress
from cryptography import x509
from cryptography.hazmat.primitives import hashes,serialization
from cryptography.x509.oid import NameOID,ExtendedKeyUsageOID
root=Path(__file__).resolve().parent
tls=root/'tls'
ca=x509.load_pem_x509_certificate((tls/'ca.crt').read_bytes())
ca_key=serialization.load_pem_private_key((tls/'ca.key').read_bytes(),password=None)
server_key=serialization.load_pem_private_key((tls/'server.key').read_bytes(),password=None)
now=datetime.now(timezone.utc)
cert=(x509.CertificateBuilder().subject_name(x509.Name([x509.NameAttribute(NameOID.COMMON_NAME,'saad-central')]))
      .issuer_name(ca.subject).public_key(server_key.public_key()).serial_number(x509.random_serial_number())
      .not_valid_before(now-timedelta(minutes=10)).not_valid_after(min(now+timedelta(days=90),ca.not_valid_after_utc))
      .add_extension(x509.BasicConstraints(ca=False,path_length=None),True)
      .add_extension(x509.ExtendedKeyUsage([ExtendedKeyUsageOID.SERVER_AUTH]),False)
      .add_extension(x509.KeyUsage(True,False,True,False,False,False,False,False,False),True)
      .add_extension(x509.AuthorityKeyIdentifier.from_issuer_public_key(ca_key.public_key()),False)
      .add_extension(x509.SubjectAlternativeName([x509.IPAddress(ipaddress.ip_address('192.168.1.23')),x509.IPAddress(ipaddress.ip_address('172.20.10.6'))]),False)
      .sign(ca_key,hashes.SHA256()))
backup=tls/('server-'+now.strftime('%Y%m%d%H%M%S')+'.crt.bak')
backup.write_bytes((tls/'server.crt').read_bytes())
(tls/'server.crt').write_bytes(cert.public_bytes(serialization.Encoding.PEM))
compose=Path(r'C:\Users\maiqo\OneDrive\Escritorio\saad-campus_evr2\saad_campus\central\compose.edge.yaml')
content=compose.read_text()
if '172.20.10.6:8443:8443' not in content and '192.168.1.23:8443:8443' not in content:
    raise RuntimeError('Unexpected port binding')
compose.write_text(content.replace('172.20.10.6:8443:8443','192.168.1.23:8443:8443'))
print('Server certificate and listener updated. CA and edge credentials preserved.')
