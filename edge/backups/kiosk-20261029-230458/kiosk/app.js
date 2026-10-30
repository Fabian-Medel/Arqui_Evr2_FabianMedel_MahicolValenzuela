'use strict';
const el = id => document.getElementById(id);
let token = '', busy = false, ready = false, cooldown = false, lastCameraSuccess = 0, currentImageURL = null, resultTimer;
const timeLabel = value => value ? new Date(value).toLocaleTimeString('es-CL') : '—';
function updateButton() { el('verify').disabled = busy || cooldown || !ready || !token; }
async function status() {
  try {
    const response = await fetch('/status', {cache:'no-store'});
    if (!response.ok) throw new Error();
    const data = await response.json(); token = data.token;
    ready = data.camera_ready && data.recognition_ready;
    el('network').textContent = data.sync_ok ? 'Central conectada' : 'Sin sincronización';
    el('network').className = `badge ${data.sync_ok ? 'online' : 'offline'}`;
    el('central').textContent = data.sync_ok ? 'Conectada' : 'Reintentando';
    el('central').title = data.sync_message;
    el('pending').textContent = data.pending;
    el('last-sync').textContent = timeLabel(data.last_sync);
    const age = data.last_policy_sync ? Date.now()-new Date(data.last_policy_sync).getTime() : Infinity;
    el('policy').textContent = age >= 0 && age <= 900000 ? 'Permisos locales vigentes · Se actualizan cada 10 s cuando hay conexión.' : 'Permisos sin vigencia. Se denegará el acceso hasta sincronizar.';
    el('camera-dot').className = ready ? 'active' : '';
    el('camera-label').textContent = ready ? 'Cámara activa' : 'Cámara no disponible';
    const history = el('history'); history.replaceChildren();
    if (!data.recent.length) { const p = document.createElement('p'); p.className = 'empty'; p.textContent = 'Aún no hay intentos.'; history.append(p); }
    for (const event of data.recent) {
      const row = document.createElement('div'); row.className = 'event';
      const name = document.createElement('b'); name.textContent = event.student_id || 'No identificado';
      const stamp = document.createElement('time'); stamp.textContent = timeLabel(event.occurred_at);
      const tag = document.createElement('span'); tag.className = `tag ${event.allowed ? '' : 'denied'}`; tag.textContent = event.allowed ? 'Autorizado' : 'Denegado';
      row.append(name, stamp, tag); history.append(row);
    }
  } catch {
    ready = false; token = '';
    el('network').textContent = 'Servicio local sin conexión'; el('network').className = 'badge offline';
    el('central').textContent = 'Sin información';
    el('camera-label').textContent = 'Sin conexión'; el('camera-dot').className = '';
  } finally { updateButton(); setTimeout(status, 2000); }
}
async function camera() {
  try {
    const response = await fetch('/camera.jpg', {cache:'no-store', signal:AbortSignal.timeout(3000)});
    if (!response.ok) throw new Error();
    const blob = await response.blob();
    const oldURL = currentImageURL; currentImageURL = URL.createObjectURL(blob);
    el('camera').src = currentImageURL; el('camera').hidden = false; el('camera-message').hidden = true;
    if (oldURL) URL.revokeObjectURL(oldURL);
    lastCameraSuccess = Date.now();
  } catch {
    if (Date.now()-lastCameraSuccess > 2000) {
      el('camera').hidden = true; el('camera-message').hidden = false;
      el('camera-message').textContent = 'Cámara no disponible. Cierra otras aplicaciones que la estén usando.';
    }
  } finally { setTimeout(camera, 140); }
}
el('verify').addEventListener('click', async () => {
  if (busy || cooldown || !ready) return;
  clearTimeout(resultTimer); busy = true; updateButton();
  el('result-card').className = 'result-card'; el('result-icon').textContent = '…';
  el('result-title').textContent = 'Verificando…'; el('result-message').textContent = 'Consultando tu identidad y permiso local.'; el('student').textContent = '';
  try {
    const response = await fetch('/verify', {method:'POST', headers:{'X-Kiosk-Token':token}});
    const result = await response.json();
    if (!response.ok) throw new Error(result.detail || 'No se pudo verificar.');
    el('result-card').className = `result-card ${result.allowed ? 'allowed' : 'denied'}`;
    el('result-icon').textContent = result.allowed ? '✓' : '×';
    el('result-title').textContent = result.allowed ? 'Acceso autorizado' : 'Acceso denegado';
    el('result-message').textContent = result.reason;
    el('student').textContent = result.student_id || 'Identidad no confirmada';
  } catch (error) {
    el('result-icon').textContent = '!'; el('result-title').textContent = 'Verificación no completada';
    el('result-message').textContent = error.message; el('student').textContent = 'No se autorizó el acceso.';
  } finally {
    busy = false; cooldown = true; updateButton();
    setTimeout(() => {cooldown = false; updateButton();}, 3000);
    resultTimer = setTimeout(() => {
      el('result-card').className = 'result-card'; el('result-icon').textContent = '◎';
      el('result-title').textContent = 'Listo para verificar'; el('result-message').textContent = 'Ubica tu rostro dentro del recuadro y presiona el botón.'; el('student').textContent = '';
    }, 10000);
  }
});
status(); camera();
