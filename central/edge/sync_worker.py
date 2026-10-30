"""Sync Worker del nodo: outbox y cursor de politica contra la API sync, por HTTPS con certificado de cliente.

Orden de cada ciclo (ADR-05): primero la politica, para que una revocacion prevalezca; despues los lotes de
eventos, que solo se marcan confirmados con los identificadores que la central devuelve.
"""
import json
import ssl
import urllib.error
import urllib.parse
import urllib.request

import config
import store

class CentralClient:
    def __init__(self, bundle=config.BUNDLE):
        conf = json.loads((bundle / 'connection.json').read_text())
        self.url, self.node_id, self._key = conf['url'], conf['node_id'], conf['api_key']
        ctx = ssl.create_default_context(cafile=str(bundle / 'ca.crt'))
        ctx.load_cert_chain(str(bundle / 'client.crt'), str(bundle / 'client.key'))
        # Ignora proxies del sistema: es una conexion directa por la red privada.
        self._opener = urllib.request.build_opener(urllib.request.ProxyHandler({}), urllib.request.HTTPSHandler(context=ctx))
        self.policy_version = None

    def request(self, path, body=None):
        headers = {'X-Node-Id': self.node_id, 'X-Node-Key': self._key, 'Content-Type': 'application/json'}
        if self.policy_version is not None: headers['X-Policy-Version'] = str(self.policy_version)
        data = None if body is None else json.dumps(body).encode()
        with self._opener.open(urllib.request.Request(self.url + path, headers=headers, data=data), timeout=config.REQUEST_TIMEOUT) as response:
            return json.load(response)

class SyncWorker:
    def __init__(self, db, client):
        self.db, self.client = db, client

    def cycle(self):
        """Devuelve los enrolamientos pendientes de este nodo."""
        last_seq = self.pull_policy()
        self.push_outbox(last_seq)
        self.push_enrollment_reports()
        return self.client.request('/edge/enrollments')['enrollments']

    def pull_policy(self):
        version = store.policy_info(self.db)['version']
        self.client.policy_version = version
        snapshot = self.client.request('/edge/policies' + ('' if version is None else f'?known_version={version}'))
        store.note_last_seq(self.db, snapshot['node_last_seq'])
        if snapshot['replace_snapshot']: store.apply_snapshot(self.db, snapshot)
        else: store.confirm_policy(self.db, snapshot['policy_version'])
        self.client.policy_version = snapshot['policy_version']
        return snapshot['node_last_seq']

    def push_outbox(self, last_seq):
        while True:
            events, actuations = store.pending(self.db)
            if not events and not actuations: return
            try:
                ack = self.client.request('/edge/batch', {'events': events, 'actuations': actuations})
            except urllib.error.HTTPError as error:
                if error.code != 409: raise
                conflict = json.load(error)['detail']
                # Reintentar el mismo lote fallaria siempre: se corrige y sigue en el proximo ciclo.
                if conflict['code'] == 'seq_conflict': store.resequence(self.db, last_seq)
                else: store.reject(self.db, conflict['ids'])
                return
            store.acknowledge(self.db, ack['accepted_ids'], ack['accepted_actuations'])

    def push_enrollment_reports(self):
        for student_id, status, detail in store.enrollment_reports(self.db):
            try:
                self.client.request('/edge/enrollments/' + urllib.parse.quote(student_id, safe=''), {'status': status, 'detail': detail})
            except urllib.error.HTTPError as error:
                if error.code != 409: raise  # 409: la central ya no espera este resultado
            store.clear_enrollment_report(self.db, student_id)
