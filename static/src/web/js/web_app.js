/*
 *  Call Recorder Web App — vanilla JS single-page application.
 *  Mirrors the textile_pos pattern: server-rendered shell + JSON-RPC endpoints.
 */
(function () {
'use strict';

// ─── State ─────────────────────────────────────────────────────────
const STATE = {
    user: window.CR_USER || {},
    currentTab: 'dashboard',
    settingsSubtab: 'voice',
    filters: {
        recordings: { device_id: '', phone: '', date_from: '', date_to: '',
                      transcription_status: '', tone_label: '', state: '' },
        tone: { channel: 'calls', api_key_id: '', date_range: 'today',
                date_from: '', date_to: '', phone_contains: '' },
    },
    cache: {
        devices: null, recordings: null,
        toneDevices: null, toneReport: null,
        keys: null, employees: null,
        voiceConfig: null, keywords: null,
    },
};

const $  = (sel, root = document) => root.querySelector(sel);
const $$ = (sel, root = document) => Array.from(root.querySelectorAll(sel));
const escapeHtml = (s) => String(s == null ? '' : s)
    .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;').replace(/'/g, '&#39;');

// ─── JSON-RPC helper ───────────────────────────────────────────────
async function rpc(url, payload = {}) {
    const body = {
        jsonrpc: '2.0', method: 'call',
        params: payload, id: Math.floor(Math.random() * 1e9),
    };
    try {
        const resp = await fetch(url, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(body),
            credentials: 'same-origin',
        });
        if (!resp.ok) {
            toast('Network error: HTTP ' + resp.status, 'danger');
            return { ok: false, error: 'HTTP ' + resp.status };
        }
        const json = await resp.json();
        if (json.error) {
            const msg = (json.error.data && json.error.data.message) || json.error.message || 'RPC error';
            toast(msg, 'danger');
            return { ok: false, error: msg };
        }
        const result = json.result;
        if (result && result.ok === false) {
            toast(result.error || 'Server error', 'danger');
        }
        return result;
    } catch (err) {
        console.error(err);
        toast('Network failure: ' + err.message, 'danger');
        return { ok: false, error: err.message };
    }
}

// ─── Toast ─────────────────────────────────────────────────────────
function toast(msg, level = 'info') {
    const region = $('#cr-toasts');
    if (!region) { console.log('[toast]', msg); return; }
    const bg = { info: 'bg-info', success: 'bg-success', danger: 'bg-danger',
                 warning: 'bg-warning text-dark' }[level] || 'bg-info';
    const el = document.createElement('div');
    el.className = 'toast align-items-center text-white ' + bg + ' border-0';
    el.setAttribute('role', 'alert');
    el.innerHTML = `
        <div class="d-flex">
            <div class="toast-body">${escapeHtml(msg)}</div>
            <button type="button" class="btn-close btn-close-white me-2 m-auto"
                    data-bs-dismiss="toast" aria-label="Close"/>
        </div>`;
    region.appendChild(el);
    const t = new bootstrap.Toast(el, { delay: 3500 });
    t.show();
    el.addEventListener('hidden.bs.toast', () => el.remove());
}

// ─── Modal ─────────────────────────────────────────────────────────
let modalInstance = null;
function modalOpen({ title, body, footer }) {
    $('#cr-modal-title').textContent = title || '';
    $('#cr-modal-body').innerHTML = body || '';
    $('#cr-modal-footer').innerHTML = footer || '';
    if (!modalInstance) modalInstance = new bootstrap.Modal($('#cr-modal'));
    modalInstance.show();
}
function modalClose() { if (modalInstance) modalInstance.hide(); }

// ─── Formatting helpers ───────────────────────────────────────────
function formatDate(dt) {
    if (!dt) return '—';
    const d = new Date(dt.replace(' ', 'T') + 'Z');
    if (isNaN(d)) return dt;
    return d.toLocaleDateString(undefined, { day: 'numeric', month: 'short' })
         + ' ' + d.toLocaleTimeString(undefined, { hour: '2-digit', minute: '2-digit' });
}
function formatRelative(dt) {
    if (!dt) return '—';
    const d = new Date(dt.replace(' ', 'T') + 'Z');
    if (isNaN(d)) return dt;
    const diff = (Date.now() - d.getTime()) / 1000;
    if (diff < 60)        return Math.round(diff) + 's ago';
    if (diff < 3600)      return Math.round(diff / 60) + 'm ago';
    if (diff < 86400)     return Math.round(diff / 3600) + 'h ago';
    if (diff < 604800)    return Math.round(diff / 86400) + 'd ago';
    return d.toLocaleDateString();
}
function dirIcon(dir) {
    if (dir === 'incoming') return '<i class="bi bi-telephone-inbound"></i>';
    if (dir === 'outgoing') return '<i class="bi bi-telephone-outbound"></i>';
    return '<i class="bi bi-telephone"></i>';
}
function formatMoney(amount) {
    const n = Number(amount || 0);
    try {
        return n.toLocaleString('en-IN', {
            style: 'currency', currency: 'INR', maximumFractionDigits: 0,
        });
    } catch (e) {
        return '₹' + Math.round(n).toLocaleString();
    }
}
function badgeTone(label) {
    if (!label) return '';
    const cls = label === 'Hard' ? 'bg-danger' : label === 'Soft' ? 'bg-success' : 'bg-warning text-dark';
    return `<span class="badge ${cls}">${escapeHtml(label)}</span>`;
}
function badgeStatus(status) {
    const map = { pending: 'bg-secondary', matched: 'bg-success',
                  unmatched: 'bg-warning text-dark', failed: 'bg-danger' };
    return `<span class="badge ${map[status] || 'bg-secondary'}">${escapeHtml(status || '—')}</span>`;
}
function badgeTranscript(s) {
    const map = { pending: 'bg-info', done: 'bg-success',
                  failed: 'bg-danger', skipped: 'bg-secondary' };
    return `<span class="badge ${map[s] || 'bg-secondary'}">${escapeHtml(s || '—')}</span>`;
}

// ─── Renderer ──────────────────────────────────────────────────────
const app = () => $('#app');
function setLoading() {
    app().innerHTML = `
        <div class="text-center text-muted py-5">
            <div class="spinner-border" role="status"></div>
            <div class="small mt-2">Loading…</div>
        </div>`;
}

// ─── Dashboard ─────────────────────────────────────────────────────
const Dashboard = {
    async render() {
        setLoading();
        const r = await rpc('/calls/api/dashboard/devices');
        if (!r || !r.ok) { app().innerHTML = '<div class="muted-empty">Failed to load.</div>'; return; }
        STATE.cache.devices = r.devices;
        const cards = r.devices.length === 0
            ? `<div class="muted-empty">No devices yet. Use the Android app to upload your first recording — it'll show here.</div>`
            : `<div class="device-grid">${r.devices.map(Dashboard.cardHTML).join('')}</div>`;
        app().innerHTML = `
            <h2 class="section-title">
                <i class="bi bi-grid-1x2 me-1"></i>Devices
                <span class="text-muted small fw-normal">(${r.devices.length})</span>
            </h2>
            ${cards}`;
        $$('.device-card').forEach(el =>
            el.addEventListener('click', () => {
                const apiId = el.dataset.apiKey;
                STATE.filters.recordings.device_id = apiId;
                go('recordings');
            }));
    },
    cardHTML(d) {
        if (d.total_calls === 0) {
            return Dashboard.placeholderCardHTML(d);
        }
        return `
            <div class="device-card" data-api-key="${d.api_key_id}">
                <div class="d-flex justify-content-between align-items-start mb-2">
                    <div class="device-title">
                        <i class="bi bi-phone me-1 text-primary"></i>${escapeHtml(d.device_name)}
                    </div>
                    ${d.employee_name
                        ? `<span class="badge bg-success">${escapeHtml(d.employee_name)}</span>`
                        : `<span class="badge bg-secondary">No employee</span>`}
                </div>
                <div class="device-stats">
                    <div class="stat stat-total"><div class="stat-value">${d.total_calls}</div><div class="stat-label">Total</div></div>
                    <div class="stat stat-out"><div class="stat-value">${d.outgoing_count}</div><div class="stat-label">Out</div></div>
                    <div class="stat stat-in"><div class="stat-value">${d.incoming_count}</div><div class="stat-label">In</div></div>
                    <div class="stat stat-harsh"><div class="stat-value">${d.harsh_calls_count}</div><div class="stat-label">Harsh</div></div>
                </div>
                <hr/>
                <div class="device-meta">
                    <span class="meta-item"><i class="bi bi-star-fill text-warning"></i>${d.avg_tone_score}/100</span>
                    <span class="meta-item"><i class="bi bi-people"></i>${d.unique_contacts_count} contacts</span>
                    <span class="meta-item"><i class="bi bi-mic-fill"></i>${d.done_transcripts_count}/${d.total_calls}</span>
                    <span class="meta-item"><i class="bi bi-clock"></i>${formatRelative(d.last_call_at)}</span>
                    ${d.last_sim_label ? `<span class="meta-item"><i class="bi bi-sim"></i>${escapeHtml(d.last_sim_label)}</span>` : ''}
                </div>
                ${d.has_wa_session ? `
                <div class="wa-block">
                    <div class="wa-counts">
                        <span><i class="bi bi-whatsapp"></i>${d.wa_message_count} msgs</span>
                        <span><i class="bi bi-emoji-smile"></i>${d.wa_tone_count} tones</span>
                        <span><i class="bi bi-journal-text"></i>${d.wa_log_count} logs</span>
                    </div>
                </div>` : ''}
            </div>`;
    },
    placeholderCardHTML(d) {
        return `
            <div class="device-card empty" data-api-key="${d.api_key_id}">
                <div class="d-flex justify-content-between align-items-start mb-2">
                    <div class="device-title">
                        <i class="bi bi-phone me-1 text-secondary"></i>${escapeHtml(d.device_name)}
                    </div>
                    ${d.employee_name
                        ? `<span class="badge bg-success">${escapeHtml(d.employee_name)}</span>`
                        : `<span class="badge bg-secondary">No employee</span>`}
                </div>
                <div class="device-empty-state">
                    <div class="device-empty-icon"><i class="bi bi-check-circle-fill text-success"></i></div>
                    <div class="device-empty-text">
                        <div class="fw-semibold small">Paired ✓</div>
                        <div class="text-muted small">
                            ${d.last_used
                                ? 'Last seen ' + formatRelative(d.last_used)
                                : 'No activity yet'}
                        </div>
                        <div class="text-muted small">No recordings yet — make a test call.</div>
                    </div>
                </div>
            </div>`;
    },
};

// ─── Recordings tab ────────────────────────────────────────────────
const Recordings = {
    async render() {
        setLoading();
        if (!STATE.cache.devices) {
            const r = await rpc('/calls/api/dashboard/devices');
            STATE.cache.devices = (r && r.ok) ? r.devices : [];
        }
        app().innerHTML = `
            ${Recordings.filtersHTML()}
            <div id="rec-list"><div class="text-center py-4"><div class="spinner-border spinner-border-sm"></div></div></div>`;
        Recordings.wireFilters();
        await Recordings.reload();
    },
    filtersHTML() {
        const f = STATE.filters.recordings;
        const deviceOpts = (STATE.cache.devices || []).map(d =>
            `<option value="${d.api_key_id}" ${String(f.device_id)==String(d.api_key_id)?'selected':''}>${escapeHtml(d.device_name)}</option>`
        ).join('');
        return `
        <div class="cr-filters">
            <div class="row g-2">
                <div class="col-6 col-md-3">
                    <label>Device</label>
                    <select class="form-select form-select-sm" id="rf-device">
                        <option value="">All devices</option>
                        ${deviceOpts}
                    </select>
                </div>
                <div class="col-6 col-md-3">
                    <label>Phone contains</label>
                    <input type="text" class="form-control form-control-sm" id="rf-phone"
                           placeholder="digits…" value="${escapeHtml(f.phone)}"/>
                </div>
                <div class="col-6 col-md-2">
                    <label>From</label>
                    <input type="date" class="form-control form-control-sm" id="rf-date-from" value="${f.date_from}"/>
                </div>
                <div class="col-6 col-md-2">
                    <label>To</label>
                    <input type="date" class="form-control form-control-sm" id="rf-date-to" value="${f.date_to}"/>
                </div>
                <div class="col-6 col-md-1">
                    <label>Tone</label>
                    <select class="form-select form-select-sm" id="rf-tone">
                        <option value="">Any</option>
                        <option value="Soft" ${f.tone_label==='Soft'?'selected':''}>Soft</option>
                        <option value="Neutral" ${f.tone_label==='Neutral'?'selected':''}>Neutral</option>
                        <option value="Hard" ${f.tone_label==='Hard'?'selected':''}>Hard</option>
                    </select>
                </div>
                <div class="col-6 col-md-1 d-flex align-items-end">
                    <button class="btn btn-sm btn-outline-secondary w-100" id="rf-clear">
                        <i class="bi bi-x-circle"></i>
                    </button>
                </div>
            </div>
        </div>`;
    },
    wireFilters() {
        const apply = () => {
            STATE.filters.recordings.device_id = $('#rf-device').value;
            STATE.filters.recordings.phone = $('#rf-phone').value;
            STATE.filters.recordings.date_from = $('#rf-date-from').value;
            STATE.filters.recordings.date_to = $('#rf-date-to').value;
            STATE.filters.recordings.tone_label = $('#rf-tone').value;
            Recordings.reload();
        };
        ['rf-device', 'rf-tone', 'rf-date-from', 'rf-date-to'].forEach(id =>
            $('#' + id).addEventListener('change', apply));
        let phoneTimer = null;
        $('#rf-phone').addEventListener('input', () => {
            clearTimeout(phoneTimer);
            phoneTimer = setTimeout(apply, 350);
        });
        $('#rf-clear').addEventListener('click', () => {
            STATE.filters.recordings = { device_id: '', phone: '', date_from: '', date_to: '',
                                         transcription_status: '', tone_label: '', state: '' };
            Recordings.render();
        });
    },
    async reload() {
        const r = await rpc('/calls/api/recordings/list', STATE.filters.recordings);
        const list = $('#rec-list');
        if (!r || !r.ok) { list.innerHTML = '<div class="muted-empty">Failed to load.</div>'; return; }
        STATE.cache.recordings = r.recordings;
        if (r.recordings.length === 0) {
            list.innerHTML = '<div class="rec-list-empty"><div style="font-size:3rem">🎙️</div>No recordings match these filters.</div>';
            return;
        }
        list.innerHTML = `<div class="bg-white rounded shadow-sm">${r.recordings.map(Recordings.rowHTML).join('')}</div>`;
        $$('.rec-row').forEach(el =>
            el.addEventListener('click', (ev) => {
                // If user tapped the phone chip or an action button, don't open the recording.
                if (ev.target.closest('[data-contact-phone]')) return;
                if (ev.target.closest('.cr-call-btn, .cr-wa-btn')) return;
                Detail.open(parseInt(el.dataset.id, 10));
            }));
        $$('[data-contact-phone]').forEach(el =>
            el.addEventListener('click', (ev) => {
                ev.stopPropagation();
                Contact.openByPhone(el.dataset.contactPhone);
            }));
        Compose.bindButtons();
    },
    rowHTML(r) {
        return `
        <div class="rec-row" data-id="${r.id}">
            <div class="rec-dir-icon rec-dir-${r.direction}">${dirIcon(r.direction)}</div>
            <div class="rec-body">
                <div class="rec-line1">
                    <div class="rec-phone">
                        <a class="contact-link" data-contact-phone="${escapeHtml(r.phone || '')}">${escapeHtml(r.phone || '—')}</a>
                        ${r.matched_partner_name
                            ? `<span class="text-muted small ms-1">· ${escapeHtml(r.matched_partner_name)}</span>` : ''}
                    </div>
                    <div class="rec-date">${formatDate(r.call_date)}</div>
                </div>
                <div class="rec-line2">
                    <span>${escapeHtml(r.duration_display)}</span>
                    ${r.device_name ? `<span><i class="bi bi-phone"></i>${escapeHtml(r.device_name)}</span>` : ''}
                    ${r.sim_label ? `<span><i class="bi bi-sim"></i>${escapeHtml(r.sim_label)}</span>` : ''}
                    ${badgeStatus(r.state)}
                    ${badgeTranscript(r.transcription_status)}
                    ${badgeTone(r.tone_label)}
                </div>
                ${r.phone ? `<div class="rec-actions mt-1">
                    ${Compose.waSendBtn(r.phone)}
                </div>` : ''}
            </div>
        </div>`;
    },
};

// ─── Recording detail (modal) ──────────────────────────────────────
const Detail = {
    async open(id) {
        modalOpen({
            title: 'Loading…',
            body: '<div class="text-center py-3"><div class="spinner-border"></div></div>',
            footer: '',
        });
        const r = await rpc('/calls/api/recordings/' + id);
        if (!r || !r.ok) return;
        Detail.renderInto(r.recording);
    },
    renderInto(rec) {
        STATE.cache.currentRec = rec;
        $('#cr-modal-title').textContent =
            `${rec.direction === 'incoming' ? '⬇' : rec.direction === 'outgoing' ? '⬆' : '·'} ${rec.phone || '—'}`;
        $('#cr-modal-body').innerHTML = `
            <div class="cr-detail">
                <div class="row g-2 mb-3 small">
                    <div class="col-6"><b>When:</b> ${formatDate(rec.call_date)}</div>
                    <div class="col-6"><b>Duration:</b> ${escapeHtml(rec.duration_display)}</div>
                    <div class="col-6"><b>Device:</b> ${escapeHtml(rec.device_name || '—')}</div>
                    <div class="col-6"><b>SIM:</b> ${escapeHtml(rec.sim_label || '—')}</div>
                    <div class="col-6"><b>Contact:</b>
                        <a class="contact-link" data-contact-phone="${escapeHtml(rec.phone || '')}">
                            ${escapeHtml(rec.matched_partner_name || rec.phone || '—')}
                        </a>
                    </div>
                    <div class="col-6"><b>Lead:</b> ${escapeHtml(rec.matched_lead_name || '—')}</div>
                    <div class="col-12">
                        <b>State:</b> ${badgeStatus(rec.state)} ·
                        <b>Transcript:</b> ${badgeTranscript(rec.transcription_status)} ·
                        <b>Tone:</b> ${badgeTone(rec.tone_label) || '—'}
                        ${rec.tone_score ? `<span class="text-muted small ms-1">(${rec.tone_score}/100)</span>` : ''}
                    </div>
                </div>

                ${rec.has_recording ? `
                <div class="audio-block">
                    <div class="small text-muted mb-1"><i class="bi bi-headphones me-1"></i>Audio</div>
                    <audio controls preload="metadata">
                        <source src="${escapeHtml(rec.audio_url)}"/>
                        Your browser doesn't support inline audio.
                    </audio>
                </div>` : `
                <div class="alert alert-warning small">No audio attached.</div>`}

                <div class="mb-2"><b class="small">Transcript</b>
                    ${rec.transcription_provider_used
                        ? `<span class="text-muted small">— ${escapeHtml(rec.transcription_provider_used)}${rec.transcription_language ? ' · ' + escapeHtml(rec.transcription_language) : ''}</span>` : ''}
                </div>
                <div class="transcript mb-3">${
                    rec.transcription_text
                        ? escapeHtml(rec.transcription_text)
                        : (rec.transcription_error
                            ? `<span class="text-danger">Error: ${escapeHtml(rec.transcription_error)}</span>`
                            : '<span class="text-muted">No transcript yet.</span>')
                }</div>

                <div class="mb-2"><b class="small">Notes</b></div>
                <textarea class="form-control form-control-sm" id="cr-detail-note" rows="2"
                          placeholder="Manual notes…">${escapeHtml(rec.note || '')}</textarea>
            </div>`;
        $('#cr-modal-footer').innerHTML = `
            ${rec.phone ? Compose.waSendBtn(rec.phone, 'WhatsApp') : ''}
            <button class="btn btn-sm btn-outline-success" data-act="convertlead">
                <i class="bi bi-bullseye"></i> Convert to Lead</button>
            <span class="flex-grow-1"></span>
            <button class="btn btn-sm btn-outline-primary" data-act="retranscribe">
                <i class="bi bi-arrow-clockwise"></i> Re-transcribe</button>
            <button class="btn btn-sm btn-outline-warning" data-act="reanalyze">
                <i class="bi bi-emoji-smile"></i> Re-analyze tone</button>
            <button class="btn btn-sm btn-outline-secondary" data-act="relink">
                <i class="bi bi-link-45deg"></i> Re-match</button>
            <button class="btn btn-sm btn-primary" data-act="savenote">
                <i class="bi bi-save"></i> Save note</button>`;
        $$('#cr-modal-footer [data-act]').forEach(b =>
            b.addEventListener('click', () => Detail.act(rec.id, b.dataset.act)));
        Compose.bindButtons($('#cr-modal-footer'));
        $$('#cr-modal-body [data-contact-phone]').forEach(el =>
            el.addEventListener('click', (ev) => {
                ev.stopPropagation();
                modalClose();
                setTimeout(() => Contact.openByPhone(el.dataset.contactPhone), 150);
            }));
    },
    async act(id, action) {
        if (action === 'savenote') {
            const note = $('#cr-detail-note').value;
            const r = await rpc('/calls/api/recordings/' + id + '/note', { note });
            if (r && r.ok) toast('Note saved.', 'success');
            return;
        }
        if (action === 'convertlead') {
            return Detail.openConvertToLead(id);
        }
        const url = '/calls/api/recordings/' + id + '/' +
            (action === 'retranscribe' ? 'retranscribe'
             : action === 'reanalyze' ? 'reanalyze_tone' : 'relink');
        const r = await rpc(url);
        if (r && r.ok) {
            toast(action + ' triggered.', 'success');
            const fresh = await rpc('/calls/api/recordings/' + id);
            if (fresh && fresh.ok) Detail.renderInto(fresh.recording);
        }
    },

    async openConvertToLead(recordingId) {
        const stagesR = await rpc('/calls/api/leads/stages');
        const stages = (stagesR && stagesR.ok) ? stagesR.stages : [];
        const stageOpts = stages.map(s =>
            `<option value="${s.id}">${escapeHtml(s.name)}</option>`).join('');
        const rec = STATE.cache.currentRec || {};
        const defaultName = 'Call from ' + (rec.matched_partner_name || rec.phone || 'unknown');
        modalOpen({
            title: 'Convert recording to lead',
            body: `
                <div class="mb-2">
                    <label class="form-label small fw-semibold">Lead title *</label>
                    <input class="form-control" id="ctl-name" value="${escapeHtml(defaultName)}"/>
                </div>
                <div class="row g-2">
                    <div class="col-6">
                        <label class="form-label small fw-semibold">Expected revenue (₹)</label>
                        <input class="form-control" type="number" id="ctl-rev" value="0" min="0"/>
                    </div>
                    <div class="col-6">
                        <label class="form-label small fw-semibold">Initial stage</label>
                        <select class="form-select" id="ctl-stage">${stageOpts}</select>
                    </div>
                </div>
                <div class="alert alert-info small mt-2 mb-0">
                    <i class="bi bi-info-circle"></i>
                    Phone, contact (if matched), and transcript will be auto-attached.
                </div>`,
            footer: `
                <button class="btn btn-secondary" data-bs-dismiss="modal">Cancel</button>
                <button class="btn btn-success" id="ctl-submit">
                    <i class="bi bi-check2"></i> Create lead</button>`,
        });
        $('#ctl-submit').addEventListener('click', async () => {
            const name = $('#ctl-name').value.trim();
            const expected_revenue = parseFloat($('#ctl-rev').value) || 0;
            const stage_id = parseInt($('#ctl-stage').value, 10) || null;
            if (!name) { toast('Title required', 'warning'); return; }
            const r = await rpc('/calls/api/leads/from_recording',
                { recording_id: recordingId, name, expected_revenue, stage_id });
            if (r && r.ok) {
                toast('Lead created.', 'success');
                modalClose();
                setTimeout(() => Pipeline.openDetail(r.lead_id), 200);
            }
        });
    },
};

// ─── Tone Report tab ───────────────────────────────────────────────
const Tone = {
    async render() {
        setLoading();
        if (!STATE.cache.toneDevices) {
            const r = await rpc('/calls/api/tone/devices');
            STATE.cache.toneDevices = (r && r.ok) ? r.devices : [];
        }
        if (!STATE.filters.tone.api_key_id && STATE.cache.toneDevices.length)
            STATE.filters.tone.api_key_id = STATE.cache.toneDevices[0].id;
        app().innerHTML = `
            <h2 class="section-title"><i class="bi bi-emoji-smile me-1"></i>Tone Report</h2>
            ${Tone.filtersHTML()}
            <div id="tone-tiles"></div>`;
        Tone.wireFilters();
        await Tone.reload();
    },
    filtersHTML() {
        const f = STATE.filters.tone;
        const devs = STATE.cache.toneDevices || [];
        const devOpts = devs.map(d =>
            `<option value="${d.id}" ${String(f.api_key_id)==String(d.id)?'selected':''}>${escapeHtml(d.name)}${d.employee_name?' — '+escapeHtml(d.employee_name):''}</option>`
        ).join('');
        const ranges = [
            ['today', 'Today'], ['yesterday', 'Yesterday'],
            ['this_week', 'This Week'], ['previous_week', 'Previous Week'],
            ['this_month', 'This Month'], ['last_month', 'Last Month'],
            ['custom', 'Custom'],
        ];
        const rangeOpts = ranges.map(([k, lbl]) =>
            `<option value="${k}" ${f.date_range===k?'selected':''}>${lbl}</option>`).join('');
        return `
        <div class="cr-filters">
            <div class="row g-2">
                <div class="col-12 col-md-4">
                    <label>Channel</label>
                    <div class="btn-group btn-group-sm w-100" role="group" id="tf-channel">
                        <input type="radio" class="btn-check" name="tf-ch" id="tf-ch-c" value="calls" ${f.channel==='calls'?'checked':''}/>
                        <label class="btn btn-outline-primary" for="tf-ch-c"><i class="bi bi-mic-fill"></i> Calls</label>
                        <input type="radio" class="btn-check" name="tf-ch" id="tf-ch-w" value="whatsapp" ${f.channel==='whatsapp'?'checked':''}/>
                        <label class="btn btn-outline-primary" for="tf-ch-w"><i class="bi bi-whatsapp"></i> WA</label>
                        <input type="radio" class="btn-check" name="tf-ch" id="tf-ch-b" value="both" ${f.channel==='both'?'checked':''}/>
                        <label class="btn btn-outline-primary" for="tf-ch-b">Both</label>
                    </div>
                </div>
                <div class="col-12 col-md-4">
                    <label>Agent (device)</label>
                    <select class="form-select form-select-sm" id="tf-device">${devOpts}</select>
                </div>
                <div class="col-6 col-md-2">
                    <label>Range</label>
                    <select class="form-select form-select-sm" id="tf-range">${rangeOpts}</select>
                </div>
                <div class="col-6 col-md-2">
                    <label>Phone contains</label>
                    <input type="text" class="form-control form-control-sm" id="tf-phone" value="${escapeHtml(f.phone_contains)}"/>
                </div>
                <div class="col-6 col-md-2" id="tf-from-wrap" style="${f.date_range==='custom'?'':'display:none'}">
                    <label>From</label>
                    <input type="date" class="form-control form-control-sm" id="tf-from" value="${f.date_from}"/>
                </div>
                <div class="col-6 col-md-2" id="tf-to-wrap" style="${f.date_range==='custom'?'':'display:none'}">
                    <label>To</label>
                    <input type="date" class="form-control form-control-sm" id="tf-to" value="${f.date_to}"/>
                </div>
            </div>
        </div>`;
    },
    wireFilters() {
        const apply = () => {
            const channel = ($('input[name=tf-ch]:checked') || {}).value || 'calls';
            STATE.filters.tone.channel = channel;
            STATE.filters.tone.api_key_id = $('#tf-device').value;
            STATE.filters.tone.date_range = $('#tf-range').value;
            STATE.filters.tone.date_from = ($('#tf-from') || {}).value || '';
            STATE.filters.tone.date_to = ($('#tf-to') || {}).value || '';
            STATE.filters.tone.phone_contains = $('#tf-phone').value;
            const isCustom = STATE.filters.tone.date_range === 'custom';
            $('#tf-from-wrap').style.display = isCustom ? '' : 'none';
            $('#tf-to-wrap').style.display = isCustom ? '' : 'none';
            Tone.reload();
        };
        $$('input[name=tf-ch]').forEach(el => el.addEventListener('change', apply));
        ['tf-device', 'tf-range'].forEach(id => $('#' + id).addEventListener('change', apply));
        ['tf-from', 'tf-to'].forEach(id => { const el = $('#'+id); if (el) el.addEventListener('change', apply); });
        let t = null;
        $('#tf-phone').addEventListener('input', () => { clearTimeout(t); t = setTimeout(apply, 350); });
    },
    async reload() {
        const tilesEl = $('#tone-tiles');
        tilesEl.innerHTML = '<div class="text-center py-3"><div class="spinner-border spinner-border-sm"></div></div>';
        const r = await rpc('/calls/api/tone/report', STATE.filters.tone);
        if (!r || !r.ok) { tilesEl.innerHTML = '<div class="muted-empty">Failed.</div>'; return; }
        if (!r.report) { tilesEl.innerHTML = '<div class="muted-empty">Select an agent.</div>'; return; }
        STATE.cache.toneReport = r.report;
        const f = STATE.filters.tone;
        const tile = (kind, emoji, label, total, calls, wa) => {
            const subbtns = `
                <div class="subbtns">
                    ${f.channel !== 'whatsapp' ? `<button class="btn btn-outline-success btn-sm" data-drill="calls" data-tone="${kind}"><i class="bi bi-mic-fill"></i> Calls <span class="badge bg-success ms-1">${calls}</span></button>` : ''}
                    ${f.channel !== 'calls' ? `<button class="btn btn-outline-success btn-sm" data-drill="wa" data-tone="${kind}"><i class="bi bi-whatsapp"></i> WhatsApp <span class="badge bg-success ms-1">${wa}</span></button>` : ''}
                </div>`;
            return `
            <div class="col-12 col-md-4">
                <div class="tone-tile tone-${kind.toLowerCase()}">
                    <div class="emoji">${emoji}</div>
                    <div class="label">${label}</div>
                    <div class="count">${total}</div>
                    ${subbtns}
                </div>
            </div>`;
        };
        tilesEl.innerHTML = `
            <div class="row g-3">
                ${tile('Soft',    '😊', 'Soft / Polite',    r.report.count_soft,    r.report.count_soft_calls,    r.report.count_soft_wa)}
                ${tile('Neutral', '😐', 'Neutral',          r.report.count_neutral, r.report.count_neutral_calls, r.report.count_neutral_wa)}
                ${tile('Hard',    '😡', 'Hard / Critical',  r.report.count_hard,    r.report.count_hard_calls,    r.report.count_hard_wa)}
            </div>
            <div class="text-center text-muted small mt-3">
                Total analyzed: <b>${r.report.count_total}</b>
            </div>`;
        $$('[data-drill]').forEach(b => b.addEventListener('click', () =>
            Tone.drill(b.dataset.drill, b.dataset.tone)));
    },
    async drill(kind, tone) {
        const payload = Object.assign({}, STATE.filters.tone, { kind, tone_label: tone });
        modalOpen({
            title: `${tone} — ${kind === 'wa' ? 'WhatsApp' : 'Calls'}`,
            body: '<div class="text-center py-3"><div class="spinner-border"/></div>',
            footer: '<button class="btn btn-secondary" data-bs-dismiss="modal">Close</button>',
        });
        const r = await rpc('/calls/api/tone/drill', payload);
        if (!r || !r.ok) return;
        if (r.items.length === 0) {
            $('#cr-modal-body').innerHTML = '<div class="muted-empty">No matches.</div>';
            return;
        }
        $('#cr-modal-body').innerHTML = `
            <div class="list-group list-group-flush">
                ${r.items.map(it => `
                    <div class="list-group-item">
                        <div class="d-flex justify-content-between">
                            <div>
                                <b>${escapeHtml(it.label || '—')}</b>
                                ${badgeTone(it.tone_label)}
                            </div>
                            <small class="text-muted">${formatDate(it.date)}</small>
                        </div>
                        ${it.kind === 'call' && it.recording_id ? `
                            <button class="btn btn-link btn-sm p-0 mt-1" data-open-rec="${it.recording_id}">
                                <i class="bi bi-headphones"></i> Open recording
                            </button>` : ''}
                    </div>`).join('')}
            </div>`;
        $$('[data-open-rec]').forEach(b => b.addEventListener('click', () => {
            modalClose();
            setTimeout(() => Detail.open(parseInt(b.dataset.openRec, 10)), 200);
        }));
    },
};

// ─── API Keys tab ──────────────────────────────────────────────────
const Keys = {
    async render() {
        setLoading();
        const r = await rpc('/calls/api/apikeys/list');
        if (!r || !r.ok) { app().innerHTML = '<div class="muted-empty">Failed.</div>'; return; }
        STATE.cache.keys = r.keys;
        app().innerHTML = `
            <div class="d-flex justify-content-between align-items-center mb-3">
                <h2 class="section-title mb-0"><i class="bi bi-key me-1"></i>API Keys</h2>
                <button class="btn btn-sm btn-primary" id="keys-add">
                    <i class="bi bi-plus-lg"></i> New Key
                </button>
            </div>
            ${r.keys.length === 0
                ? '<div class="muted-empty">No keys yet. Generate one to connect your Android app.</div>'
                : r.keys.map(Keys.rowHTML).join('')}`;
        $('#keys-add').addEventListener('click', Keys.openGenerator);
        $$('[data-revoke]').forEach(b => b.addEventListener('click', () => Keys.revoke(b.dataset.revoke)));
    },
    rowHTML(k) {
        return `
        <div class="keys-row">
            <div class="key-name">
                <i class="bi bi-${k.active ? 'phone text-primary' : 'phone text-muted'}"></i>
                ${escapeHtml(k.name)}
                ${k.active ? '' : '<span class="badge bg-secondary ms-1">Revoked</span>'}
            </div>
            <div class="key-meta">
                <span class="key-prefix">${escapeHtml(k.key_prefix || '????????')}***</span>
            </div>
            <div class="key-meta">
                <i class="bi bi-person"></i> ${escapeHtml(k.employee_name || k.user_name)}
            </div>
            <div class="key-meta">
                <i class="bi bi-clock"></i> ${k.last_used ? formatRelative(k.last_used) : 'never'}
            </div>
            <div class="key-meta">
                <i class="bi bi-mic-fill"></i> ${k.recording_count} recordings
            </div>
            ${(STATE.user.is_manager && k.active)
                ? `<button class="btn btn-sm btn-outline-danger" data-revoke="${k.id}">
                       <i class="bi bi-x-circle"></i> Revoke</button>`
                : ''}
        </div>`;
    },
    async openGenerator() {
        if (!STATE.cache.employees) {
            const r = await rpc('/calls/api/apikeys/employees');
            STATE.cache.employees = (r && r.ok) ? r.employees : [];
        }
        const empOpts = STATE.cache.employees.map(e =>
            `<option value="${e.id}">${escapeHtml(e.name)}</option>`).join('');
        modalOpen({
            title: 'Generate new API key',
            body: `
                <div class="mb-2">
                    <label class="form-label small">Device name *</label>
                    <input class="form-control" id="newkey-name" placeholder="e.g. Arun's Infinix"/>
                </div>
                <div class="mb-2">
                    <label class="form-label small">Linked employee (optional)</label>
                    <select class="form-select" id="newkey-emp">
                        <option value="">— none —</option>
                        ${empOpts}
                    </select>
                    <div class="form-text small">Setting this bridges to WhatsApp tracker — calls + WA share one dashboard.</div>
                </div>`,
            footer: `
                <button class="btn btn-secondary" data-bs-dismiss="modal">Cancel</button>
                <button class="btn btn-primary" id="newkey-submit">Generate</button>`,
        });
        $('#newkey-submit').addEventListener('click', Keys.submitGenerator);
    },
    async submitGenerator() {
        const name = $('#newkey-name').value.trim();
        const employee_id = $('#newkey-emp').value || null;
        if (!name) { toast('Name is required', 'warning'); return; }
        const r = await rpc('/calls/api/apikeys/generate', { name, employee_id });
        if (!r || !r.ok) return;
        modalOpen({
            title: '🔑 Your new API key',
            body: `
                <div class="alert alert-warning small">
                    <i class="bi bi-exclamation-triangle"></i>
                    Copy this key NOW. It will not be shown again.
                </div>
                <div class="copy-key-block" id="newkey-display">${escapeHtml(r.key)}</div>
                <button class="btn btn-sm btn-outline-primary mt-2" id="newkey-copy">
                    <i class="bi bi-clipboard"></i> Copy to clipboard
                </button>`,
            footer: `<button class="btn btn-primary" data-bs-dismiss="modal">Done</button>`,
        });
        $('#newkey-copy').addEventListener('click', () => {
            navigator.clipboard.writeText(r.key).then(() => toast('Copied.', 'success'),
                () => toast('Copy failed — select the box and copy manually.', 'warning'));
        });
        $('#cr-modal').addEventListener('hidden.bs.modal', () => Keys.render(), { once: true });
    },
    async revoke(id) {
        if (!confirm('Revoke this API key? The device will lose upload access.')) return;
        const r = await rpc('/calls/api/apikeys/' + id + '/revoke');
        if (r && r.ok) { toast('Revoked.', 'success'); Keys.render(); }
    },
};

// ─── Settings (manager) ────────────────────────────────────────────
const Settings = {
    async render() {
        if (!STATE.user.is_manager) { app().innerHTML = '<div class="muted-empty">Manager access required.</div>'; return; }
        app().innerHTML = `
            <h2 class="section-title"><i class="bi bi-gear me-1"></i>Settings</h2>
            <div class="settings-subnav">
                <button class="btn ${STATE.settingsSubtab==='voice'?'btn-primary':'btn-outline-primary'}" data-sub="voice">
                    <i class="bi bi-mic-mute"></i> Voice Transcription
                </button>
                <button class="btn ${STATE.settingsSubtab==='keywords'?'btn-primary':'btn-outline-primary'}" data-sub="keywords">
                    <i class="bi bi-tag"></i> Tone Keywords
                </button>
                <button class="btn ${STATE.settingsSubtab==='wa_sessions'?'btn-primary':'btn-outline-primary'}" data-sub="wa_sessions">
                    <i class="bi bi-whatsapp"></i> WA Sessions
                </button>
            </div>
            <div id="settings-body"></div>`;
        $$('[data-sub]').forEach(b => b.addEventListener('click', () => {
            STATE.settingsSubtab = b.dataset.sub; Settings.render();
        }));
        if (STATE.settingsSubtab === 'voice') Settings.renderVoice();
        else if (STATE.settingsSubtab === 'wa_sessions') Settings.renderWaSessions();
        else Settings.renderKeywords();
    },

    async renderWaSessions() {
        const body = $('#settings-body');
        body.innerHTML = '<div class="text-center py-3"><div class="spinner-border spinner-border-sm"></div></div>';
        const r = await rpc('/calls/api/wa/sessions/list');
        if (!r || !r.ok) { body.innerHTML = '<div class="muted-empty">Failed to load WA sessions.</div>'; return; }
        const rows = r.sessions.length === 0
            ? '<div class="muted-empty">No WhatsApp employee sessions paired yet. Click <b>Pair employee</b> to add one.</div>'
            : r.sessions.map(Settings.waSessionRowHTML).join('');
        body.innerHTML = `
            <div class="d-flex justify-content-end mb-2">
                <button class="btn btn-sm btn-primary" id="wa-sess-new">
                    <i class="bi bi-plus-lg"></i> Pair employee with WA session
                </button>
            </div>
            ${rows}`;
        $('#wa-sess-new').addEventListener('click', Settings.openWaSessionForm);
        $$('[data-wa-toggle]').forEach(b => b.addEventListener('click', () =>
            Settings.toggleWaSession(b.dataset.waToggle)));
        $$('[data-wa-delete]').forEach(b => b.addEventListener('click', () =>
            Settings.deleteWaSession(b.dataset.waDelete)));
    },

    waSessionRowHTML(s) {
        const statusColor = s.session_status === 'connected' ? 'success'
                          : s.session_status === 'disconnected' ? 'secondary'
                          : 'warning';
        return `
        <div class="keys-row">
            <div class="key-name">
                <i class="bi bi-person-circle me-1"></i>
                <b>${escapeHtml(s.employee_name)}</b>
                <span class="text-muted small ms-2">${escapeHtml(s.phone_number || '—')}</span>
            </div>
            <div class="key-meta">
                <i class="bi bi-whatsapp"></i> ${escapeHtml(s.whatsapp_session_name || '—')}
            </div>
            <div class="key-meta">
                <span class="badge bg-${statusColor}">${escapeHtml(s.session_status || 'unknown')}</span>
            </div>
            <div class="key-meta">
                <i class="bi bi-eye${s.monitoring_enabled?'-fill text-success':''}"></i>
                ${s.monitoring_enabled ? 'Monitoring' : 'Off'}
            </div>
            <div class="key-meta">
                <i class="bi bi-chat-dots"></i> ${s.total_messages} msgs
            </div>
            <div class="key-meta">
                <i class="bi bi-clock"></i> ${s.last_activity ? formatRelative(s.last_activity) : 'never'}
            </div>
            <button class="btn btn-sm btn-outline-${s.monitoring_enabled?'secondary':'success'}" data-wa-toggle="${s.id}">
                <i class="bi bi-power"></i> ${s.monitoring_enabled?'Pause':'Resume'}
            </button>
            ${STATE.user.is_manager ? `<button class="btn btn-sm btn-outline-danger" data-wa-delete="${s.id}"><i class="bi bi-trash"></i></button>` : ''}
        </div>`;
    },

    async openWaSessionForm() {
        const [waResp, empResp] = await Promise.all([
            rpc('/calls/api/wa/whatsapp_sessions'),
            rpc('/calls/api/apikeys/employees'),
        ]);
        const waList = (waResp && waResp.ok) ? waResp.sessions : [];
        const empList = (empResp && empResp.ok) ? empResp.employees : [];
        const waOpts = waList
            .filter(w => w.status === 'connected' || !w.status)
            .map(w => `<option value="${w.id}">${escapeHtml(w.name)}${w.phone_number?' · '+escapeHtml(w.phone_number):''}${w.status?' · '+escapeHtml(w.status):''}</option>`)
            .join('') || '<option value="">— no connected sessions —</option>';
        const empOpts = empList
            .map(e => `<option value="${e.id}">${escapeHtml(e.name)}</option>`)
            .join('');
        modalOpen({
            title: 'Pair employee with WhatsApp session',
            body: `
                <div class="mb-2">
                    <label class="form-label small fw-semibold">Employee *</label>
                    <select class="form-select" id="ws-emp">
                        <option value="">— pick employee —</option>
                        ${empOpts}
                    </select>
                </div>
                <div class="mb-2">
                    <label class="form-label small fw-semibold">WhatsApp session *</label>
                    <select class="form-select" id="ws-wa">
                        <option value="">— pick session —</option>
                        ${waOpts}
                    </select>
                    <div class="form-text small">Only connected neonize sessions are listed. Pair the QR in the backend first if you don't see your session.</div>
                </div>
                <div class="form-check form-switch mt-3">
                    <input type="checkbox" class="form-check-input" id="ws-mon" checked="checked"/>
                    <label class="form-check-label small" for="ws-mon">Start monitoring immediately</label>
                </div>`,
            footer: `
                <button class="btn btn-secondary" data-bs-dismiss="modal">Cancel</button>
                <button class="btn btn-primary" id="ws-submit">Pair</button>`,
        });
        $('#ws-submit').addEventListener('click', Settings.submitWaSessionForm);
    },

    async submitWaSessionForm() {
        const employee_id = $('#ws-emp').value;
        const whatsapp_session_id = $('#ws-wa').value;
        const monitoring_enabled = $('#ws-mon').checked;
        if (!employee_id || !whatsapp_session_id) {
            toast('Pick both an employee and a WhatsApp session', 'warning');
            return;
        }
        const r = await rpc('/calls/api/wa/sessions/create',
            { employee_id, whatsapp_session_id, monitoring_enabled });
        if (r && r.ok) {
            toast('Paired.', 'success');
            modalClose();
            Settings.renderWaSessions();
        }
    },

    async toggleWaSession(id) {
        const r = await rpc('/calls/api/wa/sessions/' + id + '/toggle_monitoring');
        if (r && r.ok) {
            toast(r.monitoring_enabled ? 'Monitoring on' : 'Monitoring paused', 'success');
            Settings.renderWaSessions();
        }
    },

    async deleteWaSession(id) {
        if (!confirm('Unpair this employee/session? Messages already captured stay; future ones stop syncing.')) return;
        const r = await rpc('/calls/api/wa/sessions/' + id + '/delete');
        if (r && r.ok) {
            toast('Unpaired.', 'success');
            Settings.renderWaSessions();
        }
    },
    async renderVoice() {
        const body = $('#settings-body');
        body.innerHTML = '<div class="text-center py-3"><div class="spinner-border spinner-border-sm"/></div>';
        const r = await rpc('/calls/api/voice/get');
        if (!r || !r.ok) { body.innerHTML = '<div class="muted-empty">Failed.</div>'; return; }
        const c = r.config;
        const provOpts = (val) => `
            <option value="gemini" ${val==='gemini'?'selected':''}>Google Gemini</option>
            <option value="groq"   ${val==='groq'?'selected':''}>Groq</option>
            <option value="openai" ${val==='openai'?'selected':''}>OpenAI</option>`;
        const geminiModels = ['gemini-2.5-flash','gemini-2.5-flash-lite','gemini-2.5-pro',
            'gemini-2.0-flash','gemini-2.0-flash-lite','gemini-1.5-flash','gemini-1.5-flash-8b','gemini-1.5-pro','custom'];
        const openaiModels = ['whisper-1','gpt-4o-transcribe','gpt-4o-mini-transcribe'];
        body.innerHTML = `
            <div class="card border-0 shadow-sm">
                <div class="card-body">
                    <div class="row g-3">
                        <div class="col-12 col-md-6">
                            <label class="form-label small fw-semibold">Master toggle</label>
                            <div class="form-check form-switch">
                                <input class="form-check-input" type="checkbox" id="vc-enabled"
                                       ${c.transcription_enabled?'checked':''}/>
                                <label class="form-check-label small" for="vc-enabled">Transcription enabled</label>
                            </div>
                            <div class="form-check form-switch">
                                <input class="form-check-input" type="checkbox" id="vc-translate"
                                       ${c.translate_to_english?'checked':''}/>
                                <label class="form-check-label small" for="vc-translate">Translate to English</label>
                            </div>
                        </div>
                        <div class="col-12 col-md-6">
                            <label class="form-label small fw-semibold">Provider</label>
                            <select class="form-select" id="vc-provider">${provOpts(c.transcription_provider)}</select>
                        </div>

                        <div class="col-12"><hr class="my-1"/></div>

                        <div class="col-12 col-md-6">
                            <label class="form-label small fw-semibold">Gemini API key</label>
                            <input type="password" class="form-control" id="vc-gemini-key" value="${escapeHtml(c.gemini_api_key)}"/>
                        </div>
                        <div class="col-12 col-md-6">
                            <label class="form-label small fw-semibold">Gemini model</label>
                            <select class="form-select" id="vc-gemini-model">
                                ${geminiModels.map(m => `<option value="${m}" ${c.gemini_model===m?'selected':''}>${m}</option>`).join('')}
                            </select>
                            <input class="form-control mt-1" id="vc-gemini-custom" placeholder="Custom model id"
                                   value="${escapeHtml(c.gemini_custom_model)}" ${c.gemini_model==='custom'?'':'style="display:none"'}/>
                        </div>

                        <div class="col-12 col-md-6">
                            <label class="form-label small fw-semibold">Groq API key</label>
                            <input type="password" class="form-control" id="vc-groq-key" value="${escapeHtml(c.groq_api_key)}"/>
                        </div>
                        <div class="col-12 col-md-6">
                            <label class="form-label small fw-semibold">Groq model</label>
                            <input class="form-control" id="vc-groq-model" value="${escapeHtml(c.groq_model)}"/>
                        </div>

                        <div class="col-12 col-md-6">
                            <label class="form-label small fw-semibold">OpenAI API key</label>
                            <input type="password" class="form-control" id="vc-openai-key" value="${escapeHtml(c.openai_api_key)}"/>
                        </div>
                        <div class="col-12 col-md-6">
                            <label class="form-label small fw-semibold">OpenAI model</label>
                            <select class="form-select" id="vc-openai-model">
                                ${openaiModels.map(m => `<option value="${m}" ${c.openai_model===m?'selected':''}>${m}</option>`).join('')}
                            </select>
                        </div>

                        <div class="col-12">
                            <label class="form-label small fw-semibold">ffmpeg path (optional)</label>
                            <input class="form-control" id="vc-ffmpeg" placeholder="leave blank to use $PATH"
                                   value="${escapeHtml(c.ffmpeg_path)}"/>
                            <div class="form-text small">Only needed for Groq/OpenAI when AAC files need transcoding.</div>
                        </div>

                        ${c.status_message ? `<div class="col-12"><div class="alert alert-info small mb-0">${escapeHtml(c.status_message)}</div></div>` : ''}
                    </div>
                </div>
                <div class="card-footer d-flex gap-2 justify-content-end">
                    <button class="btn btn-outline-primary" id="vc-test"><i class="bi bi-broadcast"></i> Test Connection</button>
                    <button class="btn btn-primary" id="vc-save"><i class="bi bi-save"></i> Save</button>
                </div>
            </div>`;
        $('#vc-gemini-model').addEventListener('change', e => {
            $('#vc-gemini-custom').style.display = e.target.value === 'custom' ? '' : 'none';
        });
        $('#vc-save').addEventListener('click', Settings.saveVoice);
        $('#vc-test').addEventListener('click', Settings.testVoice);
    },
    async saveVoice() {
        const vals = {
            transcription_enabled: $('#vc-enabled').checked,
            translate_to_english: $('#vc-translate').checked,
            transcription_provider: $('#vc-provider').value,
            gemini_api_key: $('#vc-gemini-key').value,
            gemini_model: $('#vc-gemini-model').value,
            gemini_custom_model: $('#vc-gemini-custom').value,
            groq_api_key: $('#vc-groq-key').value,
            groq_model: $('#vc-groq-model').value,
            openai_api_key: $('#vc-openai-key').value,
            openai_model: $('#vc-openai-model').value,
            ffmpeg_path: $('#vc-ffmpeg').value,
        };
        const r = await rpc('/calls/api/voice/save', vals);
        if (r && r.ok) toast('Voice settings saved.', 'success');
    },
    async testVoice() {
        toast('Testing connection…', 'info');
        const r = await rpc('/calls/api/voice/test');
        if (r && r.ok) {
            toast(r.status_message || 'Test complete.', 'success');
            Settings.renderVoice();
        }
    },
    async renderKeywords() {
        const body = $('#settings-body');
        body.innerHTML = '<div class="text-center py-3"><div class="spinner-border spinner-border-sm"/></div>';
        const r = await rpc('/calls/api/keywords/list');
        if (!r || !r.ok) { body.innerHTML = '<div class="muted-empty">Failed.</div>'; return; }
        STATE.cache.keywords = r.keywords;
        const catBadge = (c) =>
            c==='soft' ? '<span class="badge bg-success">Soft</span>'
            : c==='hard' ? '<span class="badge bg-danger">Hard</span>'
            : '<span class="badge bg-dark">Profanity</span>';
        body.innerHTML = `
            <div class="d-flex justify-content-end mb-2">
                <button class="btn btn-sm btn-primary" id="kw-add"><i class="bi bi-plus-lg"></i> Add Rule</button>
            </div>
            ${r.keywords.length === 0 ? '<div class="muted-empty">No keyword rules.</div>' : `
            <div class="list-group">
                ${r.keywords.map(k => `
                    <div class="list-group-item ${k.active?'':'opacity-50'}">
                        <div class="d-flex justify-content-between align-items-start">
                            <div>
                                <b>${escapeHtml(k.name)}</b> ${catBadge(k.category)}
                                <span class="badge bg-light text-dark border ms-1">${escapeHtml(k.match_type)}</span>
                                <div class="small text-muted mt-1" style="white-space:pre-wrap;max-width:600px">${escapeHtml((k.keywords||'').slice(0,150))}${k.keywords.length>150?'…':''}</div>
                            </div>
                            <div class="d-flex flex-column gap-1">
                                <button class="btn btn-sm btn-outline-secondary" data-kw-edit="${k.id}">
                                    <i class="bi bi-pencil"></i></button>
                                ${k.active ? `<button class="btn btn-sm btn-outline-danger" data-kw-del="${k.id}">
                                    <i class="bi bi-trash"></i></button>` : ''}
                            </div>
                        </div>
                    </div>`).join('')}
            </div>`}`;
        $('#kw-add').addEventListener('click', () => Settings.openKeyword(null));
        $$('[data-kw-edit]').forEach(b => b.addEventListener('click', () =>
            Settings.openKeyword(STATE.cache.keywords.find(k => k.id == b.dataset.kwEdit))));
        $$('[data-kw-del]').forEach(b => b.addEventListener('click', () => Settings.deleteKeyword(b.dataset.kwDel)));
    },
    openKeyword(kw) {
        const isNew = !kw;
        const k = kw || { name: '', category: 'soft', match_type: 'contains', keywords: '', sequence: 10, active: true };
        modalOpen({
            title: isNew ? 'Add tone keyword rule' : 'Edit rule: ' + k.name,
            body: `
                <div class="mb-2">
                    <label class="form-label small">Name *</label>
                    <input class="form-control" id="kw-name" value="${escapeHtml(k.name)}"/>
                </div>
                <div class="row g-2">
                    <div class="col-6">
                        <label class="form-label small">Category</label>
                        <select class="form-select" id="kw-cat">
                            <option value="soft" ${k.category==='soft'?'selected':''}>Soft / Polite</option>
                            <option value="hard" ${k.category==='hard'?'selected':''}>Hard / Harsh</option>
                            <option value="profanity" ${k.category==='profanity'?'selected':''}>Profanity</option>
                        </select>
                    </div>
                    <div class="col-6">
                        <label class="form-label small">Match type</label>
                        <select class="form-select" id="kw-mtype">
                            <option value="contains"   ${k.match_type==='contains'?'selected':''}>Contains</option>
                            <option value="exact_word" ${k.match_type==='exact_word'?'selected':''}>Exact Word</option>
                            <option value="regex"      ${k.match_type==='regex'?'selected':''}>Regex</option>
                        </select>
                    </div>
                </div>
                <div class="mt-2">
                    <label class="form-label small">Keywords (one per line)</label>
                    <textarea class="form-control" rows="6" id="kw-text">${escapeHtml(k.keywords)}</textarea>
                    <div class="form-text small">Case-insensitive. For regex, each line is one pattern.</div>
                </div>`,
            footer: `
                <button class="btn btn-secondary" data-bs-dismiss="modal">Cancel</button>
                <button class="btn btn-primary" id="kw-save">${isNew ? 'Create' : 'Save'}</button>`,
        });
        $('#kw-save').addEventListener('click', async () => {
            const payload = {
                id: isNew ? null : k.id,
                name: $('#kw-name').value.trim(),
                category: $('#kw-cat').value,
                match_type: $('#kw-mtype').value,
                keywords: $('#kw-text').value,
            };
            const r = await rpc('/calls/api/keywords/save', payload);
            if (r && r.ok) {
                toast('Saved.', 'success');
                modalClose();
                Settings.renderKeywords();
            }
        });
    },
    async deleteKeyword(id) {
        if (!confirm('Disable this rule?')) return;
        const r = await rpc('/calls/api/keywords/' + id + '/delete');
        if (r && r.ok) { toast('Disabled.', 'success'); Settings.renderKeywords(); }
    },
};

// ─── WhatsApp chat monitoring ──────────────────────────────────────
const WhatsApp = {
    state: {
        sessionId: localStorage.getItem('cr_wa_session') || '',
        convId:    localStorage.getItem('cr_wa_conv') || '',
        view:      'sessions',  // mobile: 'sessions' | 'convs' | 'msgs'
        sessions:  [],
        convs:     [],
        msgs:      [],
        search:    '',
    },

    async render() {
        setLoading();
        // Load sessions
        const sr = await rpc('/calls/api/wa/chat_sessions');
        WhatsApp.state.sessions = (sr && sr.ok) ? sr.sessions : [];
        if (!WhatsApp.state.sessionId && WhatsApp.state.sessions.length)
            WhatsApp.state.sessionId = String(WhatsApp.state.sessions[0].id);
        // Pre-warm Compose.sessionsCache so the bottom composer can check
        // for a connected session synchronously when rendering.
        Compose.sessionsCache = null;
        await Compose.loadSessions();
        WhatsApp.renderShell();
        await WhatsApp.loadConversations();
        if (WhatsApp.state.convId) await WhatsApp.loadMessages();
    },

    renderShell() {
        const isMobile = window.innerWidth < 768;
        app().innerHTML = `
            <div class="wa-layout ${isMobile?'wa-mobile':''} wa-view-${WhatsApp.state.view}">
                <aside class="wa-sessions-pane">
                    ${WhatsApp.sessionsPaneHTML()}
                </aside>
                <section class="wa-convs-pane">
                    ${WhatsApp.convsPaneHTML()}
                </section>
                <section class="wa-msgs-pane">
                    ${WhatsApp.msgsPaneHTML()}
                </section>
            </div>`;
        WhatsApp.wireShell();
    },

    sessionsPaneHTML() {
        const s = WhatsApp.state;
        const items = s.sessions.length === 0
            ? '<div class="muted-empty p-3">No employee sessions paired yet.</div>'
            : s.sessions.map(sess => {
                const active = String(sess.id) === String(s.sessionId);
                const statusDot = sess.status === 'connected' ? '●' : '○';
                return `
                <button class="wa-sess-row ${active?'active':''}" data-wa-pick-sess="${sess.id}">
                    <div class="wa-sess-name">
                        <span class="wa-sess-dot status-${sess.status}">${statusDot}</span>
                        ${escapeHtml(sess.name)}
                    </div>
                    <div class="wa-sess-meta">${escapeHtml(sess.phone || '')}</div>
                </button>`;
            }).join('');
        return `
            <div class="wa-pane-head"><i class="bi bi-people-fill"></i> Sessions</div>
            <div class="wa-sess-list">${items}</div>`;
    },

    convsPaneHTML() {
        const s = WhatsApp.state;
        const back = `<button class="btn btn-sm btn-link wa-back" data-wa-back="sessions">
            <i class="bi bi-arrow-left"></i> Sessions</button>`;
        if (!s.convs || s.convs.length === 0) {
            return `<div class="wa-pane-head">${back}<i class="bi bi-chat-dots"></i> Conversations</div>
                    <div class="muted-empty p-3">Pick a session to load conversations.</div>`;
        }
        const items = s.convs.map(c => {
            const active = String(c.id) === String(s.convId);
            const initial = (c.contact_name || '#').trim().charAt(0).toUpperCase();
            const groupIcon = c.is_group_message ? '<i class="bi bi-people-fill text-success me-1"></i>' : '';
            return `
            <button class="wa-conv-row ${active?'active':''}" data-wa-pick-conv="${c.id}">
                <div class="wa-conv-avatar">${escapeHtml(initial)}</div>
                <div class="wa-conv-body">
                    <div class="wa-conv-line1">
                        <span class="wa-conv-name">${groupIcon}${escapeHtml(c.contact_name)}</span>
                        <span class="wa-conv-date">${formatRelative(c.last_message_date)}</span>
                    </div>
                    <div class="wa-conv-line2">
                        <span class="wa-conv-preview">${escapeHtml((c.last_message_preview || '').slice(0, 60))}</span>
                        <span class="wa-conv-count">${c.total_messages}</span>
                    </div>
                </div>
            </button>`;
        }).join('');
        return `
            <div class="wa-pane-head">${back}<i class="bi bi-chat-dots"></i> Conversations
                <input class="wa-search" id="wa-search" placeholder="Search…" value="${escapeHtml(s.search)}"/>
            </div>
            <div class="wa-conv-list">${items}</div>`;
    },

    msgsPaneHTML() {
        const s = WhatsApp.state;
        const back = `<button class="btn btn-sm btn-link wa-back" data-wa-back="convs">
            <i class="bi bi-arrow-left"></i> Conversations</button>`;
        if (!s.convId || !s.msgs.length) {
            return `<div class="wa-pane-head">${back}<i class="bi bi-chat-text"></i> Messages</div>
                    <div class="muted-empty p-3">Pick a conversation to load messages.</div>`;
        }
        const conv = s.convs.find(c => String(c.id) === String(s.convId)) || {};
        const items = s.msgs.map(m => {
            const isOut = m.direction === 'outgoing';
            const flagged = m.is_flagged ? ' wa-flagged' : '';
            const voice = m.is_voice ?
                `<div class="wa-voice"><i class="bi bi-mic-fill"></i> Voice${m.voice_language?' ('+escapeHtml(m.voice_language)+')':''}</div>
                 ${m.voice_transcription ? '<div class="wa-voice-text">'+escapeHtml(m.voice_transcription)+'</div>' : ''}` : '';
            return `
            <div class="wa-bubble ${isOut?'out':'in'}${flagged}">
                ${voice}
                <div class="wa-text">${escapeHtml(m.text || '')}</div>
                <div class="wa-bubble-meta">${formatDate(m.date)} ${isOut && m.status?'· '+escapeHtml(m.status):''}</div>
            </div>`;
        }).join('');
        const sessionsR = Compose.sessionsCache || [];
        const hasConnected = sessionsR.some(s => s.session_status === 'connected');
        const composerDisabled = !hasConnected;
        return `
            <div class="wa-pane-head wa-sticky-head">${back}
                <div class="wa-msgs-head-info">
                    <a class="contact-link" data-contact-phone="${escapeHtml(conv.phone || '')}">
                        <b>${escapeHtml(conv.contact_name || '—')}</b>
                    </a>
                    <span class="text-muted small ms-1">${escapeHtml(conv.phone || '')}</span>
                </div>
                <div class="d-flex gap-1">
                    <button class="btn btn-sm btn-outline-secondary" id="wa-msgs-refresh">
                        <i class="bi bi-arrow-clockwise"></i>
                    </button>
                </div>
            </div>
            <div class="wa-msg-list" id="wa-msg-list">${items}</div>
            <div class="wa-composer">
                <textarea id="wa-quick-text" class="form-control"
                          rows="1" placeholder="Type a message…"
                          data-conv-phone="${escapeHtml(conv.phone || '')}"></textarea>
                <button id="wa-quick-send"
                        class="btn btn-success"
                        data-conv-phone="${escapeHtml(conv.phone || '')}"
                        ${composerDisabled ? 'disabled="disabled" title="No connected session"' : ''}>
                    <i class="bi bi-send-fill"></i>
                </button>
            </div>`;
    },

    wireShell() {
        $$('[data-wa-pick-sess]').forEach(el => el.addEventListener('click', () => {
            WhatsApp.state.sessionId = el.dataset.waPickSess;
            WhatsApp.state.convId = '';
            WhatsApp.state.msgs = [];
            WhatsApp.state.view = 'convs';
            localStorage.setItem('cr_wa_session', WhatsApp.state.sessionId);
            localStorage.removeItem('cr_wa_conv');
            WhatsApp.loadConversations();
        }));
        $$('[data-wa-pick-conv]').forEach(el => el.addEventListener('click', () => {
            WhatsApp.state.convId = el.dataset.waPickConv;
            WhatsApp.state.view = 'msgs';
            localStorage.setItem('cr_wa_conv', WhatsApp.state.convId);
            WhatsApp.loadMessages();
        }));
        $$('[data-wa-back]').forEach(el => el.addEventListener('click', () => {
            WhatsApp.state.view = el.dataset.waBack;
            WhatsApp.renderShell();
            WhatsApp.scrollToLatest();
        }));
        const searchEl = $('#wa-search');
        if (searchEl) {
            let t = null;
            searchEl.addEventListener('input', () => {
                clearTimeout(t);
                t = setTimeout(() => {
                    WhatsApp.state.search = searchEl.value;
                    WhatsApp.loadConversations();
                }, 300);
            });
        }
        const refresh = $('#wa-msgs-refresh');
        if (refresh) refresh.addEventListener('click', () => WhatsApp.loadMessages());

        // Quick-send composer at the bottom of the messages pane
        const quickText = $('#wa-quick-text');
        const quickSend = $('#wa-quick-send');
        const sendQuick = async () => {
            const phone = quickSend.dataset.convPhone;
            const text = (quickText.value || '').trim();
            if (!phone || !text) return;
            // Use the same flow as the Compose modal so the existing
            // session-picker + status-validation kicks in. If a session is
            // already known to be connected, send instantly.
            const sessions = await Compose.loadSessions();
            const connected = sessions.find(s => s.session_status === 'connected');
            if (!connected) {
                Compose.openModal(phone);
                return;
            }
            quickSend.disabled = true;
            quickSend.innerHTML = '<span class="spinner-border spinner-border-sm"></span>';
            const r = await rpc('/calls/api/wa/send_message',
                { whatsapp_session_id: connected.whatsapp_session_id, phone, text });
            quickSend.disabled = false;
            quickSend.innerHTML = '<i class="bi bi-send-fill"></i>';
            if (r && r.ok) {
                quickText.value = '';
                WhatsApp.loadMessages();
            }
        };
        if (quickSend) quickSend.addEventListener('click', sendQuick);
        if (quickText) {
            quickText.addEventListener('keydown', (ev) => {
                if (ev.key === 'Enter' && !ev.shiftKey) {
                    ev.preventDefault();
                    sendQuick();
                }
            });
            // Auto-grow textarea up to ~5 lines
            quickText.addEventListener('input', () => {
                quickText.style.height = 'auto';
                quickText.style.height = Math.min(quickText.scrollHeight, 120) + 'px';
            });
        }

        $$('[data-contact-phone]').forEach(el =>
            el.addEventListener('click', (ev) => {
                ev.stopPropagation();
                Contact.openByPhone(el.dataset.contactPhone);
            }));
        Compose.bindButtons();
    },

    async loadConversations() {
        if (!WhatsApp.state.sessionId) return;
        const r = await rpc('/calls/api/wa/chat_conversations', {
            employee_session_id: WhatsApp.state.sessionId,
            search: WhatsApp.state.search || null,
        });
        WhatsApp.state.convs = (r && r.ok) ? r.conversations : [];
        WhatsApp.renderShell();
    },

    async loadMessages() {
        if (!WhatsApp.state.convId) return;
        const r = await rpc('/calls/api/wa/chat_messages',
            { conversation_id: WhatsApp.state.convId });
        WhatsApp.state.msgs = (r && r.ok) ? r.messages : [];
        WhatsApp.renderShell();
        WhatsApp.scrollToLatest();
    },

    scrollToLatest() {
        const list = $('#wa-msg-list');
        if (list) list.scrollTop = list.scrollHeight;
    },
};

// ─── Compose — click-to-call + click-to-send-WhatsApp ─────────────
const Compose = {
    sessionsCache: null,

    telLink(phone, label) {
        const digits = String(phone || '').replace(/[^\d+]/g, '');
        if (!digits) return '';
        return `<a class="cr-call-btn btn btn-sm btn-outline-primary" href="tel:${escapeHtml(digits)}" onclick="event.stopPropagation()" title="Call ${escapeHtml(digits)}">
            <i class="bi bi-telephone-fill"></i>${label ? ' ' + escapeHtml(label) : ''}
        </a>`;
    },

    waSendBtn(phone, label) {
        const digits = String(phone || '').replace(/\D/g, '');
        if (!digits) return '';
        return `<button class="cr-wa-btn btn btn-sm btn-outline-success" data-wa-send-phone="${escapeHtml(digits)}" title="Send WhatsApp to +${escapeHtml(digits)}">
            <i class="bi bi-whatsapp"></i>${label ? ' ' + escapeHtml(label) : ''}
        </button>`;
    },

    bindButtons(root) {
        const scope = root || document;
        $$('[data-wa-send-phone]', scope).forEach(el => {
            if (el._composeBound) return;
            el._composeBound = true;
            el.addEventListener('click', (ev) => {
                ev.stopPropagation();
                Compose.openModal(el.dataset.waSendPhone);
            });
        });
    },

    async loadSessions() {
        if (Compose.sessionsCache !== null) return Compose.sessionsCache;
        const r = await rpc('/calls/api/wa/sessions/list');
        Compose.sessionsCache = (r && r.ok) ? r.sessions : [];
        return Compose.sessionsCache;
    },

    async openModal(phone, sessionIdHint) {
        // Always re-fetch — session status changes (connect / disconnect / QR)
        Compose.sessionsCache = null;
        const sessions = await Compose.loadSessions();
        if (sessions.length === 0) {
            toast('No WhatsApp sessions paired. Pair one in Settings → WA Sessions.', 'warning');
            return;
        }
        const connected = sessions.filter(s => s.session_status === 'connected');
        const fallback = connected[0] || sessions.find(s => s.monitoring_enabled) || sessions[0];
        const defaultSessId = sessionIdHint || fallback.whatsapp_session_id;
        const statusEmoji = (st) => st === 'connected' ? '🟢'
            : st === 'waiting_qr' ? '🟡'
            : st === 'reconnecting' ? '🟠'
            : st === 'error' ? '🔴' : '⚪';
        const sessOpts = sessions.map(s =>
            `<option value="${s.whatsapp_session_id}" ${String(defaultSessId)==String(s.whatsapp_session_id)?'selected':''}>
                ${statusEmoji(s.session_status)} ${escapeHtml(s.employee_name)} · ${escapeHtml(s.phone_number || '—')} (${escapeHtml(s.session_status || 'unknown')})
            </option>`).join('');
        const cleanPhone = '+' + String(phone || '').replace(/\D/g, '');
        const warnBanner = connected.length === 0
            ? `<div class="alert alert-warning small py-2 mb-2">
                  <i class="bi bi-exclamation-triangle"></i>
                  No session is currently <b>connected</b>. The send will fail unless one is live. Open Odoo backend → WhatsApp Sessions → click your session → <b>Connect</b> + scan QR.
               </div>`
            : '';
        modalOpen({
            title: `Send WhatsApp to ${cleanPhone}`,
            body: `
                ${warnBanner}
                <div class="mb-2">
                    <label class="form-label small fw-semibold">From session</label>
                    <select class="form-select" id="cm-sess">${sessOpts}</select>
                </div>
                <div class="mb-2">
                    <label class="form-label small fw-semibold">To</label>
                    <input class="form-control" id="cm-to" value="${escapeHtml(cleanPhone)}" readonly="readonly"/>
                </div>
                <div class="mb-2">
                    <label class="form-label small fw-semibold">Message *</label>
                    <textarea class="form-control" rows="4" id="cm-text" placeholder="Type your message... (Ctrl-Enter to send)" autofocus="autofocus"></textarea>
                </div>`,
            footer: `
                <button class="btn btn-secondary" data-bs-dismiss="modal">Cancel</button>
                <button class="btn btn-success" id="cm-send"><i class="bi bi-send"></i> Send</button>`,
        });
        $('#cm-send').addEventListener('click', () => Compose.submit(phone));
        $('#cm-text').addEventListener('keydown', (ev) => {
            if (ev.key === 'Enter' && (ev.ctrlKey || ev.metaKey)) {
                ev.preventDefault();
                Compose.submit(phone);
            }
        });
    },

    async submit(phone) {
        const session_id = $('#cm-sess').value;
        const text = $('#cm-text').value.trim();
        if (!session_id) { toast('Pick a session', 'warning'); return; }
        if (!text) { toast('Type a message', 'warning'); return; }
        const btn = $('#cm-send');
        btn.disabled = true;
        btn.innerHTML = '<span class="spinner-border spinner-border-sm"></span> Sending…';
        const r = await rpc('/calls/api/wa/send_message',
            { whatsapp_session_id: session_id, phone, text });
        if (r && r.ok) {
            toast('Sent.', 'success');
            modalClose();
            // If user is on WhatsApp tab viewing this contact, refresh messages.
            if (STATE.currentTab === 'whatsapp' && WhatsApp && WhatsApp.state) {
                const digits = String(phone).replace(/\D/g, '').slice(-10);
                const open = WhatsApp.state.convs.find(c =>
                    String(c.phone).replace(/\D/g, '').slice(-10) === digits);
                if (open && open.id === WhatsApp.state.convId) WhatsApp.loadMessages();
            }
        } else {
            btn.disabled = false;
            btn.innerHTML = '<i class="bi bi-send"></i> Send';
        }
    },
};

// ─── Contact 360 — unified per-contact overlay ─────────────────────
const Contact = {
    state: { key: null, profile: null, items: [], filter: 'all', loading: false },

    async openByPhone(phone) {
        if (!phone) return;
        const r = await rpc('/calls/api/contact/lookup', { phone });
        if (!r || !r.ok) return;
        Contact.open(r.key);
    },

    async openByPartner(partnerId) {
        if (!partnerId) return;
        const r = await rpc('/calls/api/contact/lookup', { partner_id: partnerId });
        if (!r || !r.ok) return;
        Contact.open(r.key);
    },

    open(key) {
        Contact.state.key = key;
        Contact.state.filter = 'all';
        Contact.state.profile = null;
        Contact.state.items = [];
        Contact.show();
        Contact.loadProfile();
        Contact.loadTimeline();
    },

    show() {
        let overlay = $('#cr-contact-overlay');
        if (!overlay) {
            overlay = document.createElement('div');
            overlay.id = 'cr-contact-overlay';
            overlay.className = 'cr-contact-overlay';
            document.body.appendChild(overlay);
        }
        overlay.classList.add('open');
        Contact.render();
    },

    close() {
        const overlay = $('#cr-contact-overlay');
        if (overlay) overlay.classList.remove('open');
    },

    async loadProfile() {
        const r = await rpc('/calls/api/contact/' + encodeURIComponent(Contact.state.key) + '/profile');
        if (!r || !r.ok) return;
        Contact.state.profile = r.profile;
        Contact.render();
    },

    async loadTimeline() {
        Contact.state.loading = true;
        Contact.render();
        const r = await rpc('/calls/api/contact/' + encodeURIComponent(Contact.state.key) + '/timeline',
            { filter: Contact.state.filter });
        Contact.state.loading = false;
        if (!r || !r.ok) { Contact.state.items = []; Contact.render(); return; }
        Contact.state.items = r.items || [];
        Contact.render();
    },

    setFilter(f) {
        Contact.state.filter = f;
        Contact.loadTimeline();
    },

    render() {
        const overlay = $('#cr-contact-overlay');
        if (!overlay) return;
        const p = Contact.state.profile;
        const headerHTML = p ? `
            <div class="contact-header">
                <div class="contact-avatar">
                    ${p.image
                        ? `<img src="${escapeHtml(p.image)}" alt="" onerror="this.style.display='none'"/>`
                        : '<i class="bi bi-person-circle"></i>'}
                </div>
                <div class="contact-id">
                    <div class="contact-name">${escapeHtml(p.display_name || 'Unknown')}</div>
                    <div class="contact-phone">
                        <i class="bi bi-telephone"></i> ${escapeHtml(p.phone || '—')}
                        ${p.email ? `<span class="ms-3"><i class="bi bi-envelope"></i> ${escapeHtml(p.email)}</span>` : ''}
                    </div>
                    ${p.phone ? `
                        <div class="contact-actions mt-2">
                            ${Compose.waSendBtn(p.phone, 'WhatsApp')}
                        </div>` : ''}
                </div>
                <div class="contact-kpi-strip">
                    <div class="kpi"><div class="kpi-val">${p.kpis.calls_total}</div><div class="kpi-lbl">Calls</div></div>
                    <div class="kpi"><div class="kpi-val text-danger">${p.kpis.calls_harsh}</div><div class="kpi-lbl">Harsh</div></div>
                    <div class="kpi"><div class="kpi-val text-success">${p.kpis.wa_messages}</div><div class="kpi-lbl">WA Msgs</div></div>
                    <div class="kpi"><div class="kpi-val text-primary">${p.kpis.leads_count}</div><div class="kpi-lbl">Leads</div></div>
                </div>
            </div>` : '<div class="text-center py-4"><div class="spinner-border spinner-border-sm"></div></div>';

        const filters = ['all', 'calls', 'wa', 'leads', 'activities'];
        const filterLabels = { all: 'All', calls: 'Calls', wa: 'WhatsApp', leads: 'Leads', activities: 'Activities' };
        const subnav = `
            <div class="contact-subnav">
                ${filters.map(f => `
                    <button class="btn btn-sm ${Contact.state.filter===f?'btn-primary':'btn-outline-secondary'}" data-cf="${f}">
                        ${filterLabels[f]}
                    </button>`).join('')}
            </div>`;

        const timelineHTML = Contact.state.loading
            ? '<div class="text-center py-3"><div class="spinner-border spinner-border-sm"></div></div>'
            : (Contact.state.items.length === 0
                ? '<div class="muted-empty">Nothing here yet.</div>'
                : `<div class="contact-timeline">${Contact.state.items.map(Contact.itemHTML).join('')}</div>`);

        overlay.innerHTML = `
            <div class="contact-card">
                <div class="contact-topbar">
                    <button class="btn btn-sm btn-light" id="cr-contact-close">
                        <i class="bi bi-x-lg"></i> Close
                    </button>
                </div>
                ${headerHTML}
                ${subnav}
                <div class="contact-body">${timelineHTML}</div>
            </div>`;
        $('#cr-contact-close').addEventListener('click', Contact.close);
        $$('[data-cf]').forEach(b =>
            b.addEventListener('click', () => Contact.setFilter(b.dataset.cf)));
        $$('[data-contact-open-rec]').forEach(b =>
            b.addEventListener('click', () => Detail.open(parseInt(b.dataset.contactOpenRec, 10))));
        Compose.bindButtons(overlay);
    },

    itemHTML(it) {
        const icon = it.type === 'call'
            ? (it.direction === 'incoming' ? 'bi-telephone-inbound text-success'
              : it.direction === 'outgoing' ? 'bi-telephone-outbound text-primary'
              : 'bi-telephone')
            : it.type === 'wa' ? 'bi-whatsapp text-success'
            : it.type === 'lead' ? 'bi-bullseye text-primary'
            : it.type === 'activity' ? 'bi-bell text-warning'
            : 'bi-circle';
        const typeBadge = it.type === 'call' ? '<span class="badge bg-light text-dark">Call</span>'
            : it.type === 'wa' ? '<span class="badge bg-success">WA</span>'
            : it.type === 'lead' ? '<span class="badge bg-primary">Lead</span>'
            : it.type === 'activity' ? '<span class="badge bg-warning text-dark">Activity</span>'
            : '';
        const action = it.type === 'call'
            ? `<button class="btn btn-link btn-sm p-0" data-contact-open-rec="${it.id}">Open recording</button>`
            : '';
        return `
        <div class="contact-tl-item">
            <div class="tl-icon"><i class="bi ${icon}"></i></div>
            <div class="tl-body">
                <div class="tl-head">
                    ${typeBadge}
                    <span class="tl-title">${escapeHtml(it.title || '')}</span>
                    <span class="tl-date">${formatDate(it.date)}</span>
                </div>
                ${it.preview ? `<div class="tl-preview">${escapeHtml(it.preview)}</div>` : ''}
                ${it.tone_label ? badgeTone(it.tone_label) : ''}
                ${action}
            </div>
        </div>`;
    },
};

// ─── Pipeline — kanban of crm.lead ─────────────────────────────────
const Pipeline = {
    state: { stages: [], leadsByStage: {}, search: '', loading: false },
    drag: { leadId: null, sourceStageId: null },

    async render() {
        await Pipeline.load();
        app().innerHTML = `
            <div class="cr-pipeline">
                <div class="d-flex gap-2 mb-3 align-items-center">
                    <input id="pipe-search" class="form-control form-control-sm" style="max-width:280px;"
                           placeholder="Search leads (name, phone, contact)…" value="${escapeHtml(Pipeline.state.search)}"/>
                    <button id="pipe-refresh" class="btn btn-sm btn-outline-secondary">
                        <i class="bi bi-arrow-clockwise"></i>
                    </button>
                    <span class="ms-auto small text-muted">
                        Drag cards between columns to move stages.
                    </span>
                </div>
                <div class="kanban-board" id="kanban-board">
                    ${Pipeline.state.stages.map(Pipeline.columnHTML).join('')}
                </div>
            </div>`;
        Pipeline.bind();
    },

    rerenderColumns() {
        const board = $('#kanban-board');
        if (!board) return;
        board.innerHTML = Pipeline.state.stages.map(Pipeline.columnHTML).join('');
        Pipeline.bind();
    },

    async load() {
        Pipeline.state.loading = true;
        const s = await rpc('/calls/api/leads/stages');
        Pipeline.state.stages = (s && s.ok) ? s.stages : [];
        const byStage = {};
        for (const st of Pipeline.state.stages) {
            const r = await rpc('/calls/api/leads/list', {
                stage_id: st.id, search: Pipeline.state.search || null,
            });
            byStage[st.id] = (r && r.ok) ? r.leads : [];
        }
        Pipeline.state.leadsByStage = byStage;
        Pipeline.state.loading = false;
    },

    columnHTML(stage) {
        const leads = Pipeline.state.leadsByStage[stage.id] || [];
        const totalRev = leads.reduce((s, ld) => s + (ld.expected_revenue || 0), 0);
        return `
        <div class="kanban-col" data-stage-id="${stage.id}">
            <div class="kanban-col-head">
                <div>
                    <div class="kanban-col-name">${escapeHtml(stage.name)}</div>
                    <div class="kanban-col-meta">${leads.length} · ${formatMoney(totalRev)}</div>
                </div>
                <span class="badge bg-light text-dark">${leads.length}</span>
            </div>
            <div class="kanban-col-body" data-stage-id="${stage.id}">
                ${leads.length === 0
                    ? '<div class="muted-empty small text-center py-3">Empty</div>'
                    : leads.map(Pipeline.cardHTML).join('')}
            </div>
        </div>`;
    },

    cardHTML(ld) {
        const priorityStars = '★'.repeat(parseInt(ld.priority || '0', 10));
        return `
        <div class="kanban-card" draggable="true" data-lead-id="${ld.id}" data-stage-id="${ld.stage_id}">
            <div class="kanban-card-title">${escapeHtml(ld.name)}</div>
            <div class="kanban-card-sub">
                ${ld.partner_name ? `<i class="bi bi-person"></i> ${escapeHtml(ld.partner_name)}` : ''}
                ${ld.phone ? `· ${escapeHtml(ld.phone)}` : ''}
            </div>
            <div class="kanban-card-foot">
                <span class="kanban-rev">${formatMoney(ld.expected_revenue)}</span>
                ${priorityStars ? `<span class="kanban-prio">${priorityStars}</span>` : ''}
                ${ld.recording_count ? `<span class="badge bg-info text-dark">${ld.recording_count} calls</span>` : ''}
            </div>
        </div>`;
    },

    bind() {
        const search = $('#pipe-search');
        if (search) {
            let t = null;
            search.addEventListener('input', () => {
                clearTimeout(t);
                t = setTimeout(() => {
                    Pipeline.state.search = search.value;
                    Pipeline.render();
                }, 300);
            });
        }
        const refresh = $('#pipe-refresh');
        if (refresh) refresh.addEventListener('click', () => Pipeline.render());

        // Card click → open detail
        $$('.kanban-card').forEach(card => {
            card.addEventListener('click', (ev) => {
                if (ev.target.closest('.kanban-card[draggable]') && card._dragging) return;
                Pipeline.openDetail(parseInt(card.dataset.leadId, 10));
            });
            card.addEventListener('dragstart', (ev) => {
                Pipeline.drag.leadId = parseInt(card.dataset.leadId, 10);
                Pipeline.drag.sourceStageId = parseInt(card.dataset.stageId, 10);
                card._dragging = true;
                card.classList.add('dragging');
                ev.dataTransfer.effectAllowed = 'move';
            });
            card.addEventListener('dragend', () => {
                card._dragging = false;
                card.classList.remove('dragging');
            });
        });

        // Column body = drop target
        $$('.kanban-col-body').forEach(body => {
            body.addEventListener('dragover', (ev) => {
                ev.preventDefault();
                ev.dataTransfer.dropEffect = 'move';
                body.classList.add('drag-over');
            });
            body.addEventListener('dragleave', () => body.classList.remove('drag-over'));
            body.addEventListener('drop', async (ev) => {
                ev.preventDefault();
                body.classList.remove('drag-over');
                const targetStageId = parseInt(body.dataset.stageId, 10);
                const leadId = Pipeline.drag.leadId;
                const sourceStageId = Pipeline.drag.sourceStageId;
                if (!leadId || targetStageId === sourceStageId) return;

                // Optimistic move — pop the lead from source array, push to target,
                // then re-render immediately. RPC fires in background.
                const sourceList = Pipeline.state.leadsByStage[sourceStageId] || [];
                const idx = sourceList.findIndex(ld => ld.id === leadId);
                if (idx >= 0) {
                    const [moved] = sourceList.splice(idx, 1);
                    const targetStage = Pipeline.state.stages.find(s => s.id === targetStageId);
                    moved.stage_id = targetStageId;
                    moved.stage_name = targetStage ? targetStage.name : moved.stage_name;
                    (Pipeline.state.leadsByStage[targetStageId] = Pipeline.state.leadsByStage[targetStageId] || []).unshift(moved);
                    Pipeline.rerenderColumns();
                }

                const r = await rpc('/calls/api/leads/' + leadId + '/move_stage',
                    { stage_id: targetStageId });
                if (r && r.ok) {
                    toast('Stage updated.', 'success');
                } else {
                    // Rollback on failure
                    toast('Move failed; reverting.', 'danger');
                    Pipeline.render();
                }
            });
        });
    },

    // ─── Lead detail modal ─────────────────────────────────────────
    async openDetail(leadId) {
        modalOpen({ title: 'Loading…', body: '<div class="text-center py-3"><div class="spinner-border spinner-border-sm"></div></div>', footer: '' });
        const r = await rpc('/calls/api/leads/' + leadId);
        if (!r || !r.ok) {
            $('#cr-modal-body').innerHTML = '<div class="alert alert-danger">' + (r ? escapeHtml(r.error || 'Error') : 'Failed') + '</div>';
            return;
        }
        Pipeline.renderDetail(r);
    },

    renderDetail(data) {
        const ld = data.lead;
        const recs = data.recordings || [];
        const wa = data.wa_logs || [];
        const acts = data.activities || [];
        $('#cr-modal-title').innerHTML = `<i class="bi bi-bullseye text-primary"></i> ${escapeHtml(ld.name)}`;
        $('#cr-modal-body').innerHTML = `
            <div class="row g-2 mb-3 small">
                <div class="col-md-6"><b>Contact:</b>
                    ${ld.phone
                        ? `<a class="contact-link" data-contact-phone="${escapeHtml(ld.phone)}">${escapeHtml(ld.partner_name || ld.phone)}</a>`
                        : escapeHtml(ld.partner_name || '—')}
                </div>
                <div class="col-md-6"><b>Phone:</b> ${escapeHtml(ld.phone || '—')}</div>
                <div class="col-md-6"><b>Stage:</b> <span class="badge bg-primary">${escapeHtml(ld.stage_name || '—')}</span></div>
                <div class="col-md-6"><b>Revenue:</b> ${formatMoney(ld.expected_revenue)} · ${ld.probability}%</div>
                <div class="col-md-6"><b>Salesperson:</b> ${escapeHtml(ld.user_name || '—')}</div>
                <div class="col-md-6"><b>Team:</b> ${escapeHtml(ld.team_name || '—')}</div>
            </div>
            ${ld.description ? `<div class="mb-3"><b class="small">Description</b><div class="small text-muted" style="white-space:pre-wrap;">${escapeHtml(ld.description)}</div></div>` : ''}
            <div class="lead-tabs">
                <button class="btn btn-sm btn-primary active" data-ld-tab="recs">
                    <i class="bi bi-telephone"></i> Recordings (${recs.length})
                </button>
                <button class="btn btn-sm btn-outline-primary" data-ld-tab="wa">
                    <i class="bi bi-whatsapp"></i> WhatsApp (${wa.length})
                </button>
                <button class="btn btn-sm btn-outline-primary" data-ld-tab="acts">
                    <i class="bi bi-bell"></i> Activities (${acts.length})
                </button>
            </div>
            <div id="ld-tab-content" class="mt-2">
                ${Pipeline._tabContent('recs', recs, wa, acts)}
            </div>`;
        $('#cr-modal-footer').innerHTML = `
            ${ld.phone ? Compose.waSendBtn(ld.phone, 'WhatsApp') : ''}
            <span class="flex-grow-1"></span>
            <button class="btn btn-sm btn-outline-danger" data-ld-act="lost">
                <i class="bi bi-x-circle"></i> Lost</button>
            <button class="btn btn-sm btn-success" data-ld-act="won">
                <i class="bi bi-trophy"></i> Mark Won</button>`;

        // Wire interactions
        $$('[data-ld-tab]').forEach(b =>
            b.addEventListener('click', () => {
                $$('[data-ld-tab]').forEach(x => {
                    x.classList.toggle('btn-primary', x.dataset.ldTab === b.dataset.ldTab);
                    x.classList.toggle('btn-outline-primary', x.dataset.ldTab !== b.dataset.ldTab);
                    x.classList.toggle('active', x.dataset.ldTab === b.dataset.ldTab);
                });
                $('#ld-tab-content').innerHTML = Pipeline._tabContent(b.dataset.ldTab, recs, wa, acts);
                Pipeline._wireTabInteractions();
            }));
        $$('[data-ld-act]').forEach(b =>
            b.addEventListener('click', () => Pipeline.act(ld.id, b.dataset.ldAct)));
        Compose.bindButtons($('#cr-modal-footer'));
        Pipeline._wireTabInteractions();
    },

    _tabContent(tab, recs, wa, acts) {
        if (tab === 'recs') {
            return recs.length === 0
                ? '<div class="muted-empty small">No linked recordings.</div>'
                : `<div class="small">${recs.map(r => `
                    <div class="lead-link-row" data-open-rec="${r.id}">
                        <span><i class="bi bi-telephone"></i> ${escapeHtml(r.phone)}</span>
                        <span class="text-muted">${escapeHtml(r.duration_display)}</span>
                        ${badgeTone(r.tone_label)}
                        <span class="text-muted">${formatDate(r.call_date)}</span>
                    </div>`).join('')}</div>`;
        }
        if (tab === 'wa') {
            return wa.length === 0
                ? '<div class="muted-empty small">No WhatsApp messages.</div>'
                : `<div class="small">${wa.map(l => `
                    <div class="lead-link-row">
                        <span class="badge ${l.direction==='incoming'?'bg-secondary':'bg-success'}">${l.direction}</span>
                        <span class="text-truncate" style="max-width:60%;">${escapeHtml(l.text || '')}</span>
                        <span class="text-muted ms-auto">${formatDate(l.date)}</span>
                    </div>`).join('')}</div>`;
        }
        if (tab === 'acts') {
            return acts.length === 0
                ? '<div class="muted-empty small">No activities scheduled.</div>'
                : `<div class="small">${acts.map(a => `
                    <div class="lead-link-row">
                        <span><i class="bi bi-bell"></i> ${escapeHtml(a.summary || a.type)}</span>
                        <span class="text-muted ms-auto">Due ${escapeHtml(a.date_deadline || '—')}</span>
                        ${a.user_name ? `<span class="badge bg-light text-dark">${escapeHtml(a.user_name)}</span>` : ''}
                    </div>`).join('')}</div>`;
        }
        return '';
    },

    _wireTabInteractions() {
        $$('[data-open-rec]').forEach(el =>
            el.addEventListener('click', () => {
                modalClose();
                setTimeout(() => Detail.open(parseInt(el.dataset.openRec, 10)), 150);
            }));
    },

    async act(leadId, action) {
        if (action === 'won') {
            const r = await rpc('/calls/api/leads/' + leadId + '/mark_won');
            if (r && r.ok) { toast('Marked as Won.', 'success'); modalClose(); Pipeline.render(); }
        } else if (action === 'lost') {
            if (!confirm('Mark this lead as Lost?')) return;
            const r = await rpc('/calls/api/leads/' + leadId + '/mark_lost');
            if (r && r.ok) { toast('Marked as Lost.', 'info'); modalClose(); Pipeline.render(); }
        }
    },
};

// ─── Router ────────────────────────────────────────────────────────
const TABS = { dashboard: Dashboard, recordings: Recordings, tone: Tone,
               whatsapp: WhatsApp, pipeline: Pipeline,
               apikeys: Keys, settings: Settings };

function go(tabName) {
    if (!TABS[tabName]) tabName = 'dashboard';
    STATE.currentTab = tabName;
    $$('.cr-tab').forEach(el => el.classList.toggle('active', el.dataset.tab === tabName));
    // Full-bleed layout for WhatsApp + Pipeline; other tabs keep the
    // centered max-width container.
    const fullBleed = (tabName === 'whatsapp' || tabName === 'pipeline');
    document.body.classList.toggle('wa-fullscreen', fullBleed);
    TABS[tabName].render();
}

// ─── Notifications — bell icon + dropdown ──────────────────────────
const Notifications = {
    state: { items: [], unread: 0, lastSeen: '', open: false, loading: false },
    pollTimer: null,
    busBound: false,

    async init() {
        const bell = $('#cr-bell');
        if (!bell) return;
        bell.addEventListener('click', (ev) => {
            ev.stopPropagation();
            Notifications.toggle();
        });
        // Close on outside-click
        document.addEventListener('click', (ev) => {
            const dd = $('#cr-bell-dropdown');
            if (!dd) return;
            if (dd.contains(ev.target) || $('#cr-bell').contains(ev.target)) return;
            Notifications.closeDropdown();
        });
        await Notifications.fetch();
        // Light fallback polling every 60s in case bus push misses
        Notifications.pollTimer = setInterval(Notifications.fetch, 60000);
        Notifications.bindBus();
    },

    bindBus() {
        if (Notifications.busBound) return;
        Notifications.busBound = true;
        // Try Odoo's bus_service if it's available globally. If not,
        // fall back to the 60s poll (already set in init).
        try {
            const odooEnv = window.odoo && window.odoo.__DEBUG__ && window.odoo.__DEBUG__.services;
            const bus = (odooEnv && odooEnv.bus_service) || null;
            if (!bus) return;
            bus.addChannel('crm_call_recorder.alert');
            bus.addChannel('wa.tracker.update');
            bus.addEventListener('notification', (ev) => {
                if (!Array.isArray(ev.detail)) return;
                for (const n of ev.detail) {
                    if (n.type === 'harsh_tone' || n.type === 'wa.message.created') {
                        Notifications.fetch();
                        break;
                    }
                }
            });
        } catch (e) {
            console.warn('Notifications: bus subscription unavailable; using poll only.', e);
        }
    },

    async fetch() {
        const r = await rpc('/calls/api/notifications/list', { limit: 50 });
        if (!r || !r.ok) return;
        Notifications.state.items = r.notifications || [];
        Notifications.state.unread = r.unread || 0;
        Notifications.state.lastSeen = r.last_seen || '';
        Notifications.renderBadge();
        if (Notifications.state.open) Notifications.renderDropdown();
    },

    renderBadge() {
        const badge = $('#cr-bell-badge');
        if (!badge) return;
        if (Notifications.state.unread > 0) {
            badge.textContent = Notifications.state.unread > 99 ? '99+' : Notifications.state.unread;
            badge.style.display = '';
        } else {
            badge.style.display = 'none';
        }
    },

    async toggle() {
        if (Notifications.state.open) {
            Notifications.closeDropdown();
        } else {
            await Notifications.openDropdown();
        }
    },

    async openDropdown() {
        Notifications.state.open = true;
        Notifications.renderDropdown();
        // Mark read on open
        await rpc('/calls/api/notifications/mark_read');
        Notifications.state.unread = 0;
        Notifications.renderBadge();
    },

    closeDropdown() {
        Notifications.state.open = false;
        const dd = $('#cr-bell-dropdown');
        if (dd) dd.remove();
    },

    renderDropdown() {
        let dd = $('#cr-bell-dropdown');
        if (!dd) {
            dd = document.createElement('div');
            dd.id = 'cr-bell-dropdown';
            dd.className = 'cr-bell-dropdown';
            document.body.appendChild(dd);
            // Position below bell
            const bell = $('#cr-bell');
            if (bell) {
                const r = bell.getBoundingClientRect();
                dd.style.top = (r.bottom + 6) + 'px';
                dd.style.right = (window.innerWidth - r.right) + 'px';
            }
        }
        const items = Notifications.state.items;
        if (items.length === 0) {
            dd.innerHTML = '<div class="cr-bell-empty"><i class="bi bi-check-circle text-success"></i> All caught up.</div>';
            return;
        }
        dd.innerHTML = `
            <div class="cr-bell-head">
                <b>Notifications</b>
                <span class="text-muted small">${items.length}</span>
            </div>
            <div class="cr-bell-list">
                ${items.map(Notifications.itemHTML).join('')}
            </div>`;
        $$('.cr-bell-item', dd).forEach(el =>
            el.addEventListener('click', () => Notifications.handleItemClick(el.dataset.kind, el.dataset.payload)));
    },

    itemHTML(it) {
        const icon = it.kind === 'harsh_tone' ? 'bi-fire text-danger'
            : it.kind === 'unanswered_wa' ? 'bi-whatsapp text-success'
            : it.kind === 'overdue_activity' ? 'bi-bell text-warning'
            : it.kind === 'unmatched_rec' ? 'bi-link-45deg text-secondary'
            : 'bi-info-circle';
        const isUnread = (it.date || '') > (Notifications.state.lastSeen || '');
        const payload = JSON.stringify({
            recording_id: it.recording_id || 0,
            conversation_id: it.conversation_id || 0,
            employee_session_id: it.employee_session_id || 0,
            phone: it.phone || '',
            res_model: it.res_model || '',
            res_id: it.res_id || 0,
        });
        return `
        <div class="cr-bell-item ${isUnread?'unread':''}" data-kind="${escapeHtml(it.kind)}" data-payload='${escapeHtml(payload)}'>
            <div class="cr-bell-icon"><i class="bi ${icon}"></i></div>
            <div class="cr-bell-body">
                <div class="cr-bell-title">${escapeHtml(it.title || '')}</div>
                <div class="cr-bell-sub">${escapeHtml(it.subtitle || '')}</div>
                <div class="cr-bell-date">${formatRelative(it.date)}</div>
            </div>
        </div>`;
    },

    handleItemClick(kind, payloadJson) {
        let payload;
        try { payload = JSON.parse(payloadJson); } catch(e) { payload = {}; }
        Notifications.closeDropdown();
        if (kind === 'harsh_tone' || kind === 'unmatched_rec') {
            if (payload.recording_id) Detail.open(payload.recording_id);
        } else if (kind === 'unanswered_wa') {
            // Open WhatsApp tab and jump to conversation
            go('whatsapp');
            setTimeout(() => {
                if (payload.employee_session_id) {
                    WhatsApp.state.sessionId = payload.employee_session_id;
                    WhatsApp.loadConversations().then(() => {
                        if (payload.conversation_id) {
                            WhatsApp.state.convId = payload.conversation_id;
                            WhatsApp.loadMessages();
                        }
                    });
                }
            }, 200);
        } else if (kind === 'overdue_activity') {
            // Best-effort: open Contact 360 via res_id if it's a partner
            if (payload.res_model === 'res.partner' && payload.res_id) {
                Contact.openByPartner(payload.res_id);
            } else if (payload.res_model === 'crm.call.recording' && payload.res_id) {
                Detail.open(payload.res_id);
            } else {
                toast('Open the activity in Odoo backend.', 'info');
            }
        }
    },
};

// ─── Boot ──────────────────────────────────────────────────────────
document.addEventListener('DOMContentLoaded', () => {
    $$('.cr-tab').forEach(el => el.addEventListener('click', () => go(el.dataset.tab)));
    go('dashboard');
    Notifications.init();
});

})();
