const state = { data: null, filter: 'ALL', query: '' };
const $ = (id) => document.getElementById(id);
const statusLabels = {
  URGENT: 'ต้องจัดการด่วน',
  UNPAID: 'มียอดค้าง',
  ATTENTION: 'ระบบเช็กไม่ได้',
  CLEAR: 'ปกติ',
  NOT_CHECKED: 'ยังไม่ตรวจ'
};

function escapeHtml(value) {
  return String(value ?? '').replace(/[&<>'"]/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;',"'":'&#39;','"':'&quot;'}[c]));
}

function fmtMoney(value) {
  if (value === null || value === undefined || Number.isNaN(Number(value))) return '-';
  return new Intl.NumberFormat('th-TH', { style: 'currency', currency: 'THB', maximumFractionDigits: 0 }).format(Number(value));
}

function fmtDate(value, includeTime = true) {
  if (!value) return '-';
  const d = new Date(value);
  if (Number.isNaN(d.getTime())) return '-';
  const options = includeTime
    ? { day:'2-digit', month:'short', hour:'2-digit', minute:'2-digit', timeZone:'Asia/Bangkok' }
    : { day:'2-digit', month:'short', year:'numeric', timeZone:'Asia/Bangkok' };
  return new Intl.DateTimeFormat('th-TH', options).format(d);
}

function toast(message) {
  const el = $('toast');
  el.textContent = message;
  el.classList.add('show');
  setTimeout(() => el.classList.remove('show'), 2600);
}

function statusPill(status) {
  return `<span class="status-pill status-${escapeHtml(status)}">${escapeHtml(statusLabels[status] || status)}</span>`;
}

function isVisible(vehicle) {
  const q = state.query.trim().toLowerCase();
  const haystack = `${vehicle.plate_number} ${vehicle.province} ${vehicle.driver_name}`.toLowerCase();
  if (q && !haystack.includes(q)) return false;
  if (state.filter === 'ALL') return true;
  if (state.filter === 'ACTION') return ['URGENT', 'UNPAID', 'ATTENTION'].includes(vehicle.status);
  return vehicle.status === state.filter;
}

function renderFleet(data) {
  const vehicles = data.vehicles.filter(isVisible);
  const rows = $('fleetRows');
  const mobile = $('mobileFleet');
  if (!vehicles.length) {
    rows.innerHTML = '<tr><td colspan="7" class="empty-state">ไม่พบรถตามตัวกรอง</td></tr>';
    mobile.innerHTML = '<div class="empty-state">ไม่พบรถตามตัวกรอง</div>';
    return;
  }

  rows.innerHTML = vehicles.map(v => {
    const deadlineClass = v.status === 'URGENT' ? 'deadline urgent' : 'deadline';
    const action = v.payment_url ? `<a class="action-link" href="${escapeHtml(v.payment_url)}" target="_blank" rel="noopener">เปิด M-Flow</a>` : '';
    return `<tr>
      <td><span class="plate">${escapeHtml(v.plate_number)}</span><span class="subline">${escapeHtml(v.province)}</span></td>
      <td>${escapeHtml(v.driver_name || '-')}</td>
      <td>${statusPill(v.status)}</td>
      <td><span class="amount">${fmtMoney(v.outstanding_amount)}</span><span class="subline">${v.outstanding_count ? `${v.outstanding_count} รายการ` : ''}</span></td>
      <td class="${deadlineClass}">${fmtDate(v.nearest_deadline)}</td>
      <td>${fmtDate(v.last_checked)}</td>
      <td>${action}</td>
    </tr>`;
  }).join('');

  mobile.innerHTML = vehicles.map(v => {
    const action = v.payment_url ? `<a class="action-link" href="${escapeHtml(v.payment_url)}" target="_blank" rel="noopener">เปิด M-Flow</a>` : '';
    return `<article class="mobile-card">
      <div class="mobile-card-head"><div><span class="plate">${escapeHtml(v.plate_number)}</span><span class="subline">${escapeHtml(v.province)} · ${escapeHtml(v.driver_name || '-')}</span></div>${statusPill(v.status)}</div>
      <div class="mobile-card-grid">
        <div class="mobile-field"><span>ยอดค้าง</span><strong>${fmtMoney(v.outstanding_amount)}</strong></div>
        <div class="mobile-field"><span>ครบกำหนดภายใน</span><strong>${fmtDate(v.nearest_deadline)}</strong></div>
        <div class="mobile-field"><span>ตรวจล่าสุด</span><strong>${fmtDate(v.last_checked)}</strong></div>
      </div>
      <div class="mobile-actions">${action}</div>
    </article>`;
  }).join('');
}

function render(data) {
  state.data = data;
  $('urgentCount').textContent = data.summary.urgent;
  $('unpaidCount').textContent = data.summary.unpaid;
  $('attentionCount').textContent = data.summary.attention;
  $('clearCount').textContent = data.summary.clear;
  $('totalVehicles').textContent = `(${data.summary.total})`;
  $('lastUpdated').textContent = data.last_updated ? `ข้อมูลล่าสุด ${fmtDate(data.last_updated)}` : 'ยังไม่มีข้อมูลการตรวจ';

  const badge = $('modeBadge');
  badge.textContent = data.mode === 'DEMO' ? 'DEMO · ข้อมูลทดสอบ' : 'LIVE · ข้อมูลจริง';
  badge.className = `mode-badge ${data.mode.toLowerCase()}`;

  const banner = $('systemBanner');
  const button = $('checkButton');
  banner.classList.toggle('running', data.run.running);
  banner.classList.toggle('error', Boolean(data.run.last_error));
  button.disabled = data.run.running;
  button.textContent = data.run.running ? 'กำลังตรวจสอบ...' : 'ตรวจสอบตอนนี้';
  if (data.run.running) $('systemText').textContent = 'ระบบกำลังตรวจรถทั้งหมด กรุณารอสักครู่ หน้านี้จะอัปเดตเอง';
  else if (data.run.last_error) $('systemText').textContent = `รอบล่าสุดมีปัญหา: ${data.run.last_error}`;
  else if (data.run.last_finished) $('systemText').textContent = `ระบบพร้อมใช้งาน · ตรวจรอบล่าสุด ${fmtDate(data.run.last_finished)}`;
  else $('systemText').textContent = 'ระบบพร้อมใช้งาน กด “ตรวจสอบตอนนี้” เพื่อเริ่มรอบแรก';

  const demoPanel = $('demoPanel');
  if (data.mode === 'DEMO') {
    demoPanel.classList.remove('hidden');
    const notifications = data.demo_notifications || [];
    $('notificationList').innerHTML = notifications.length
      ? notifications.slice().reverse().map(n => `<div class="notification-item">${escapeHtml(n)}</div>`).join('')
      : '<div class="empty-state">กดตรวจสอบเพื่อดูตัวอย่างข้อความแจ้งเตือน</div>';
  } else {
    demoPanel.classList.add('hidden');
  }
  renderFleet(data);
}

async function loadSummary(silent = false) {
  try {
    const response = await fetch('/api/summary', { cache: 'no-store' });
    if (!response.ok) throw new Error(`HTTP ${response.status}`);
    render(await response.json());
  } catch (error) {
    if (!silent) toast(`โหลดข้อมูลไม่ได้: ${error.message}`);
    $('systemBanner').classList.add('error');
    $('systemText').textContent = 'เชื่อมต่อ backend ไม่สำเร็จ';
  }
}

async function runCheck() {
  $('checkButton').disabled = true;
  try {
    const response = await fetch('/api/check', { method: 'POST' });
    const body = await response.json();
    if (!response.ok) throw new Error(body.error || `HTTP ${response.status}`);
    toast(body.started ? 'เริ่มตรวจรถทั้งหมดแล้ว' : 'มีรอบตรวจทำงานอยู่แล้ว');
    await loadSummary(true);
  } catch (error) {
    toast(`เริ่มตรวจไม่ได้: ${error.message}`);
    $('checkButton').disabled = false;
  }
}

$('checkButton').addEventListener('click', runCheck);
$('searchInput').addEventListener('input', e => { state.query = e.target.value; if (state.data) renderFleet(state.data); });
document.querySelectorAll('.filter-chip').forEach(button => {
  button.addEventListener('click', () => {
    document.querySelectorAll('.filter-chip').forEach(b => b.classList.remove('active'));
    button.classList.add('active');
    state.filter = button.dataset.filter;
    if (state.data) renderFleet(state.data);
  });
});

loadSummary();
setInterval(() => loadSummary(true), 5000);
