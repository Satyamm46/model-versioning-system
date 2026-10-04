/* Tiny single-page app: hash routing + fetch to the REST API. No framework. */
const $app = document.getElementById('app');
const $user = document.getElementById('user');
$user.value = localStorage.getItem('mvs_user') || '';
$user.addEventListener('change', () => localStorage.setItem('mvs_user', $user.value.trim()));
const me = () => $user.value.trim() || 'anonymous';

const esc = s => String(s ?? '').replace(/[&<>"']/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
const badge = s => `<span class="badge ${esc(s)}">${esc(s)}</span>`;
const fmtDate = d => d ? new Date(d).toLocaleString() : '-';
const pct = a => a == null ? '-' : Number(a).toFixed(1) + '%';
const mb = b => (b / 1048576).toFixed(2) + ' MB';

async function api(path, opts = {}) {
  const res = await fetch('/api' + path, opts);
  let data = null;
  try { data = await res.json(); } catch (e) { /* no body */ }
  if (!res.ok) {
    const d = data && data.detail;
    throw new Error(Array.isArray(d) ? d.map(x => x.msg).join('; ') : (d || res.statusText));
  }
  return data;
}
const post = (path, body) => api(path, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) });

let toastTimer;
function toast(msg, ok = true) {
  const t = document.getElementById('toast');
  t.textContent = msg; t.className = 'toast show ' + (ok ? 'ok' : 'err');
  clearTimeout(toastTimer); toastTimer = setTimeout(() => t.className = 'toast', 4500);
}

/* ---------------------------------------------------------------- pages */
async function dashboardPage() {
  const d = await api('/dashboard');
  $app.innerHTML = `
    <h1>Dashboard</h1>
    <div class="stats">
      <div class="stat"><b>${d.total_models}</b><span>Total models</span></div>
      <div class="stat"><b>${d.total_versions}</b><span>Total versions</span></div>
      <div class="stat"><b>${d.production_models}</b><span>Production models</span></div>
      <div class="stat bad"><b>${d.failed_versions}</b><span>Failed versions</span></div>
    </div>
    <div class="card"><h2>Latest versions</h2>
      ${d.versions.length ? `<div class="tablewrap"><table>
        <tr><th>Model</th><th>Version</th><th>Accuracy</th><th>Status</th><th>Uploaded by</th><th>Date</th></tr>
        ${d.versions.map(v => `<tr>
          <td><a href="#/models/${v.model_id}">${esc(v.model_name)}</a></td><td>v${v.version}</td>
          <td>${pct(v.accuracy)}</td><td>${badge(v.status)}</td><td>${esc(v.created_by)}</td><td>${fmtDate(v.created_at)}</td></tr>`).join('')}
      </table></div>` : '<p class="muted">No versions yet. Register a model on the <a href="#/models">Models</a> page and upload its first version.</p>'}
    </div>`;
}

async function modelsPage() {
  const models = await api('/models');
  $app.innerHTML = `
    <h1>Models</h1>
    <div class="card"><h2>Registered models</h2>
      ${models.length ? `<div class="tablewrap"><table>
        <tr><th>Name</th><th>Type</th><th>Versions</th><th>Production</th><th>Created by</th><th>Created</th></tr>
        ${models.map(m => `<tr><td><a href="#/models/${m.id}">${esc(m.name)}</a></td><td>${esc(m.model_type) || '-'}</td>
          <td>${m.version_count}</td><td>${m.production_version ? 'v' + m.production_version : '-'}</td>
          <td>${esc(m.created_by)}</td><td>${fmtDate(m.created_at)}</td></tr>`).join('')}
      </table></div>` : '<p class="muted">No models registered yet.</p>'}
    </div>
    <div class="card"><h2>Register a new model</h2>
      <form id="newModel" class="grid">
        <label>Model name<input name="name" required maxlength="100" placeholder="Student Performance Predictor"></label>
        <label>Model type<input name="model_type" maxlength="50" placeholder="Random Forest"></label>
        <label class="full">Description<input name="description" maxlength="500"></label>
        <label>First version file (.pkl / .joblib)<input type="file" name="file" accept=".pkl,.joblib"></label>
        <label>Accuracy of first version (%)<input type="number" name="accuracy" min="0" max="100" step="0.1"></label>
        <label class="full">Change notes<input name="change_notes" maxlength="500" placeholder="Initial version"></label>
        <div class="full"><button type="submit">Register model</button></div>
      </form>
    </div>`;
  document.getElementById('newModel').addEventListener('submit', async e => {
    e.preventDefault();
    const f = new FormData(e.target);
    try {
      const m = await post('/models', { name: f.get('name'), description: f.get('description'),
        model_type: f.get('model_type'), created_by: me() });
      const file = f.get('file');
      if (file && file.size) {
        const fd = new FormData();
        fd.append('file', file); fd.append('accuracy', f.get('accuracy')); fd.append('created_by', me());
        fd.append('change_notes', f.get('change_notes'));
        if (!fd.get('accuracy')) fd.delete('accuracy');
        await api(`/models/${m.id}/versions`, { method: 'POST', body: fd });
      }
      toast('Model registered'); location.hash = `#/models/${m.id}`;
    } catch (err) { toast(err.message, false); }
  });
}

async function modelPage(id) {
  const [m, versions, deps] = await Promise.all([api(`/models/${id}`), api(`/models/${id}/versions`), api(`/models/${id}/deployments`)]);
  const prod = versions.find(v => v.status === 'PRODUCTION');
  const opts = versions.map(v => `<option value="${v.version}">v${v.version}</option>`).join('');
  $app.innerHTML = `
    <div class="row spread"><h1>${esc(m.name)}</h1>
      ${m.production_version ? '' : `<button class="danger small" onclick="deleteModel(${m.id})">Delete model</button>`}</div>
    <div class="card"><dl class="facts">
      <div><dt>Description</dt><dd>${esc(m.description) || '-'}</dd></div>
      <div><dt>Model type</dt><dd>${esc(m.model_type) || '-'}</dd></div>
      <div><dt>Current production version</dt><dd>${m.production_version ? 'v' + m.production_version : 'None'}</dd></div>
      <div><dt>Production accuracy</dt><dd>${pct(m.production_accuracy)}</dd></div>
      <div><dt>Number of versions</dt><dd>${m.version_count}</dd></div>
      <div><dt>Last deployment</dt><dd>${fmtDate(m.last_deployment)}</dd></div>
    </dl></div>

    <div class="card"><div class="row spread"><h2>Version history</h2>
      ${versions.length >= 2 ? `<div class="row">Compare
        <select id="cmpA">${opts}</select> with <select id="cmpB">${opts}</select>
        <button class="small ghost" onclick="goCompare(${m.id})">Compare</button></div>` : ''}</div>
      ${versions.length ? `<div class="tablewrap"><table>
        <tr><th>Version</th><th>Accuracy</th><th>Size</th><th>Status</th><th>Uploaded by</th><th>Date</th><th>Change notes</th><th>Actions</th></tr>
        ${versions.map(v => versionRow(v, m, prod)).join('')}
      </table></div>` : '<p class="muted">No versions yet. Upload the first one below.</p>'}
    </div>

    <div class="card"><h2>Upload new version</h2>
      <form id="upload" class="grid">
        <label>Model file (.pkl / .joblib)<input type="file" name="file" accept=".pkl,.joblib" required></label>
        <label>Accuracy (%)<input type="number" name="accuracy" min="0" max="100" step="0.1"></label>
        <label class="full">Change notes<input name="change_notes" maxlength="500" placeholder="What changed in this version?"></label>
        <div class="full"><button type="submit">Upload (next version number is automatic)</button></div>
      </form>
    </div>

    <div class="card"><h2>Deployment history for this model</h2>${deploymentsTable(deps, false)}</div>`;

  document.getElementById('upload').addEventListener('submit', async e => {
    e.preventDefault();
    const fd = new FormData(e.target);
    fd.append('created_by', me());
    if (!fd.get('accuracy')) fd.delete('accuracy');
    try {
      const v = await api(`/models/${id}/versions`, { method: 'POST', body: fd });
      toast(v.status === 'FAILED' ? `v${v.version} saved but FAILED validation: ${v.validation_message}` : `v${v.version} uploaded and validated`, v.status !== 'FAILED');
      render();
    } catch (err) { toast(err.message, false); }
  });
}

/* Buttons only appear when they are logically valid. */
function versionRow(v, m, prod) {
  const btn = [`<a class="btn small ghost" href="#/versions/${v.id}">View</a>`];
  if (prod && prod.id !== v.id) btn.push(`<a class="btn small ghost" href="#/models/${m.id}/compare?a=${v.version}&b=${prod.version}">Compare</a>`);
  if (v.status !== 'PRODUCTION' && v.status !== 'FAILED') btn.push(`<button class="small" onclick="promote(${v.id})">Promote</button>`);
  if (v.status === 'PRODUCTION' && m.rollback_target) btn.push(`<button class="small danger" onclick="rollback(${m.id}, ${m.rollback_target})">Rollback to v${m.rollback_target}</button>`);
  return `<tr><td>v${v.version}</td><td>${pct(v.accuracy)}</td><td>${mb(v.file_size)}</td><td>${badge(v.status)}</td>
    <td>${esc(v.created_by)}</td><td>${fmtDate(v.created_at)}</td><td class="wrap">${esc(v.change_notes) || '-'}</td>
    <td><div class="actions">${btn.join('')}</div></td></tr>`;
}

function deploymentsTable(rows, withModel) {
  if (!rows.length) return '<p class="muted">No deployments yet.</p>';
  return `<div class="tablewrap"><table>
    <tr>${withModel ? '<th>Model</th>' : ''}<th>Version</th><th>Action</th><th>Status</th><th>User</th><th>Date</th><th>Notes</th></tr>
    ${rows.map(d => `<tr>${withModel ? `<td><a href="#/models/${d.model_id}">${esc(d.model_name)}</a></td>` : ''}
      <td>v${d.version}</td><td>${badge(d.action)}</td><td>${badge(d.status)}</td><td>${esc(d.deployed_by)}</td>
      <td>${fmtDate(d.deployment_time)}</td><td class="wrap">${esc(d.notes)}</td></tr>`).join('')}
  </table></div>`;
}

async function comparePage(id, params) {
  const a = params.get('a'), b = params.get('b');
  const c = await api(`/models/${id}/compare?a=${encodeURIComponent(a)}&b=${encodeURIComponent(b)}`);
  const imp = c.accuracy_improvement;
  const row = (label, fa, fb) => `<tr><td>${label}</td><td>${fa}</td><td>${fb}</td></tr>`;
  $app.innerHTML = `
    <p><a href="#/models/${id}">← ${esc(c.model)}</a></p>
    <h1>Compare v${c.a.version} vs v${c.b.version}</h1>
    <div class="card"><table>
      <tr><th>Attribute</th><th>v${c.a.version}</th><th>v${c.b.version}</th></tr>
      ${row('Accuracy', pct(c.a.accuracy), pct(c.b.accuracy))}
      ${row('Size', mb(c.a.file_size), mb(c.b.file_size))}
      ${row('Status', badge(c.a.status), badge(c.b.status))}
      ${row('Uploaded by', esc(c.a.created_by), esc(c.b.created_by))}
      ${row('Created date', fmtDate(c.a.created_at), fmtDate(c.b.created_at))}
      ${row('Change notes', esc(c.a.change_notes) || '-', esc(c.b.change_notes) || '-')}
    </table>
    <p><b>Accuracy improvement:</b> ${imp == null ? 'not available (accuracy missing)' :
      `<span class="${imp >= 0 ? 'up' : 'down'}">${imp >= 0 ? '+' : ''}${imp}%</span>`}</p></div>`;
}

async function versionPage(id) {
  const v = await api(`/versions/${id}`);
  $app.innerHTML = `
    <p><a href="#/models/${v.model_id}">← ${esc(v.model_name)}</a></p>
    <h1>${esc(v.model_name)} v${v.version} ${badge(v.status)}</h1>
    <div class="card"><dl class="facts">
      <div><dt>Accuracy</dt><dd>${pct(v.accuracy)}</dd></div>
      <div><dt>File</dt><dd>${esc(v.file_path)}</dd></div>
      <div><dt>Size</dt><dd>${mb(v.file_size)}</dd></div>
      <div><dt>Uploaded by</dt><dd>${esc(v.created_by)}</dd></div>
      <div><dt>Upload date</dt><dd>${fmtDate(v.created_at)}</dd></div>
      <div><dt>Validation result</dt><dd>${esc(v.validation_message)}</dd></div>
      <div><dt>Change notes</dt><dd>${esc(v.change_notes) || '-'}</dd></div>
    </dl></div>`;
}

async function deploymentsPage() {
  const rows = await api('/deployments');
  $app.innerHTML = `<h1>Deployment history</h1><div class="card">${deploymentsTable(rows, true)}</div>`;
}

/* -------------------------------------------------------------- actions */
window.goCompare = id => {
  const a = document.getElementById('cmpA').value, b = document.getElementById('cmpB').value;
  if (a === b) return toast('Pick two different versions', false);
  location.hash = `#/models/${id}/compare?a=${a}&b=${b}`;
};
window.promote = async vid => {
  if (!confirm('Promote this version to PRODUCTION? The current production version will be archived.')) return;
  try { const v = await post(`/versions/${vid}/promote`, { performed_by: me() }); toast(`v${v.version} is now in production`); }
  catch (err) { toast(err.message, false); }
  render();
};
window.rollback = async (mid, target) => {
  const reason = prompt(`Roll back to v${target}? Enter a reason (optional):`);
  if (reason === null) return;
  try { const r = await post(`/models/${mid}/rollback`, { performed_by: me(), reason }); toast(`${r.message} ${r.summary}`); }
  catch (err) { toast(err.message, false); }
  render();
};
window.deleteModel = async id => {
  if (!confirm('Delete this model and all of its versions?')) return;
  try { await api(`/models/${id}`, { method: 'DELETE' }); toast('Model deleted'); location.hash = '#/models'; }
  catch (err) { toast(err.message, false); }
};

/* --------------------------------------------------------------- router */
async function render() {
  const [path, qs] = (location.hash.slice(1) || '/').split('?');
  const parts = path.split('/').filter(Boolean);
  document.querySelectorAll('#nav a').forEach(a => a.classList.toggle('active', a.dataset.page === (parts[0] || '')));
  try {
    if (!parts.length) await dashboardPage();
    else if (parts[0] === 'models' && parts.length === 1) await modelsPage();
    else if (parts[0] === 'models' && parts[2] === 'compare') await comparePage(parts[1], new URLSearchParams(qs || ''));
    else if (parts[0] === 'models') await modelPage(parts[1]);
    else if (parts[0] === 'versions') await versionPage(parts[1]);
    else if (parts[0] === 'deployments') await deploymentsPage();
    else $app.innerHTML = '<div class="card">Page not found.</div>';
  } catch (err) { $app.innerHTML = `<div class="card err">${esc(err.message)}</div>`; }
}
window.addEventListener('hashchange', render);
render();
