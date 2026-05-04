/* FTP 估算卡片邏輯
 *
 * 三個 UI 狀態：
 *   A - 尚未估算：顯示目前 FTP，只有「估算 FTP」按鈕
 *   B - 有建議值：三欄比較 + 子模型 + 套用/複製
 *   C - 已套用：目前 FTP + ✓ 已套用 badge + 重新運算/複製
 */

let _ftpSuggestData = null;

function _fmtDuration(sec) {
  const m = Math.floor(sec / 60);
  const s = sec % 60;
  return `${m}:${String(s).padStart(2, '0')}`;
}

// ── 錯誤訊息（取代 alert）────────────────────────────────────────────────

function _showError(msg) {
  const box = document.getElementById('ftpErrorMsg');
  document.getElementById('ftpErrorText').textContent = msg;
  box.classList.remove('hidden');
  setTimeout(() => box.classList.add('hidden'), 5000);
}

function _hideError() {
  document.getElementById('ftpErrorMsg').classList.add('hidden');
}

// ── 狀態切換 ─────────────────────────────────────────────────────────────

function _showState(state) {
  const submodels  = document.getElementById('ftpSubmodels');
  const applyWrap  = document.getElementById('ftpApplyWrap');
  const copyWrap   = document.getElementById('ftpCopyWrap');
  const applyBtn   = document.getElementById('ftpApplyBtn');
  const label      = document.getElementById('ftpSuggestBtnLabel');

  // 預設全收
  submodels.classList.add('hidden');
  applyWrap.classList.add('hidden');
  copyWrap.classList.add('hidden');

  if (state === 'A' || state === 'nodata') {
    label.textContent = '估算 FTP';
    return;
  }

  // B / C：子模型區顯示
  submodels.classList.remove('hidden');
  copyWrap.classList.remove('hidden');
  label.textContent = '重新運算';

  if (state === 'B') {
    applyWrap.classList.remove('hidden');
    applyBtn.disabled = false;
    applyBtn.textContent = '套用建議值';
  } else if (state === 'C') {
    applyWrap.classList.remove('hidden');
    applyBtn.disabled = true;
    applyBtn.textContent = '已套用';
  }
}

// ── 主值區渲染 ───────────────────────────────────────────────────────────

function _renderValuesB(data) {
  const deltaColor = data.delta > 0 ? 'text-emerald-400'
    : data.delta < 0 ? 'text-rose-400'
    : 'text-zinc-400';
  const deltaPrefix = data.delta > 0 ? '+' : '';

  document.getElementById('ftpValuesSection').innerHTML = `
    <div class="grid grid-cols-3 divide-x divide-white/6">
      <div class="px-5 py-4 text-center">
        <p class="text-[10px] text-zinc-500 uppercase tracking-wider font-mono mb-2">目前</p>
        <p class="text-3xl font-black font-mono text-zinc-400 leading-none">${data.ftp_current ?? '—'}</p>
        <p class="text-[10px] text-zinc-600 font-mono mt-1.5">W</p>
      </div>
      <div class="px-5 py-4 text-center">
        <p class="text-[10px] text-zinc-500 uppercase tracking-wider font-mono mb-2">建議</p>
        <p class="text-3xl font-black font-mono text-zinc-100 leading-none">${data.ftp_final ?? '—'}</p>
        <p class="text-[10px] text-zinc-600 font-mono mt-1.5">W</p>
      </div>
      <div class="px-5 py-4 text-center">
        <p class="text-[10px] text-zinc-500 uppercase tracking-wider font-mono mb-2">差值</p>
        <p class="text-3xl font-black font-mono ${deltaColor} leading-none">${deltaPrefix}${data.delta ?? '—'}</p>
        <p class="text-[10px] text-zinc-600 font-mono mt-1.5">W</p>
      </div>
    </div>`;
}

function _renderValuesC(data) {
  document.getElementById('ftpValuesSection').innerHTML = `
    <div class="px-6 py-5 flex items-center gap-4">
      <div>
        <div class="flex items-baseline gap-2">
          <span class="text-5xl font-black font-mono text-zinc-100 leading-none">${data.ftp_current ?? '—'}</span>
          <span class="text-sm text-zinc-500 font-mono">W</span>
        </div>
        <p class="text-[10px] text-zinc-500 uppercase tracking-wider font-mono mt-1.5">目前 FTP</p>
      </div>
      <span class="flex items-center gap-1.5 text-xs text-emerald-400 bg-emerald-500/10 border border-emerald-500/20 px-2.5 py-1 rounded-full font-medium shrink-0">
        <svg class="w-3 h-3" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="2.5">
          <path stroke-linecap="round" stroke-linejoin="round" d="M5 13l4 4L19 7"/>
        </svg>
        已套用
      </span>
    </div>`;
}

function _renderValuesA(currentFtp) {
  document.getElementById('ftpValuesSection').innerHTML = `
    <div class="px-6 py-6">
      <div class="flex items-baseline gap-2 mb-1.5">
        <span class="text-5xl font-black font-mono text-zinc-100">${currentFtp ?? '—'}</span>
        <span class="text-sm text-zinc-500 font-mono">W</span>
      </div>
      <p class="text-[10px] text-zinc-500 uppercase tracking-wider font-mono">目前 FTP</p>
      <p class="text-xs text-zinc-600 mt-3 leading-relaxed">分析近 90 天功率資料，推算更準確的 FTP</p>
    </div>`;
}

function _renderValuesNoData() {
  document.getElementById('ftpValuesSection').innerHTML = `
    <div class="px-6 py-6 text-center">
      <p class="text-sm text-zinc-500">90 天內無足夠功率資料，無法估算 FTP。</p>
      <p class="text-xs text-zinc-600 mt-1">需要有功率計的 15–40 分鐘騎乘記錄。</p>
    </div>`;
}

// ── Header badge ─────────────────────────────────────────────────────────

function _updateBadge(data) {
  const badge = document.getElementById('ftpHeaderBadge');
  const ts    = document.getElementById('ftpSuggestTimestamp');
  const wkg   = document.getElementById('ftpWperKgBadge');

  if (!data) {
    badge.textContent = '';
    ts.classList.add('hidden');
    wkg.classList.add('hidden');
    return;
  }

  const applied = data.delta === 0;
  if (applied) {
    badge.textContent = `${data.ftp_current} W · 已套用`;
  } else if (data.ftp_final) {
    const sign = data.delta > 0 ? '+' : '';
    badge.textContent = `${data.ftp_current} W → ${data.ftp_final} W (${sign}${data.delta})`;
  } else {
    badge.textContent = `${data.ftp_current} W`;
  }

  if (data.weight_kg && data.ftp_current) {
    wkg.textContent = `${(data.ftp_current / data.weight_kg).toFixed(2)} W/kg`;
    wkg.classList.remove('hidden');
  }

  if (data.generated_at) {
    ts.textContent = data.generated_at;
    ts.classList.remove('hidden');
  }
}

// ── 子模型內容渲染 ───────────────────────────────────────────────────────

function _renderMmp(data) {
  if (data.ftp_mmp && data.mmp_detail) {
    const d = data.mmp_detail;
    document.getElementById('ftpMmpVal').textContent = `${data.ftp_mmp} W`;
    document.getElementById('ftpMmpBasis').innerHTML =
      `${d.basis_activity_name}<br>` +
      `${d.basis_date} · ${_fmtDuration(d.basis_duration_sec)} · NP ${d.basis_np} W · ×${d.coeff}`;
  } else {
    document.getElementById('ftpMmpVal').textContent = '—';
    document.getElementById('ftpMmpBasis').textContent = '無足夠功率資料';
  }
}

function _renderPhysicsResult(ftp_physics, physics_detail) {
  if (ftp_physics && physics_detail) {
    const best = physics_detail.basis_activities[0];
    document.getElementById('ftpPhysVal').textContent = `${ftp_physics} W`;
    document.getElementById('ftpPhysBasis').innerHTML =
      `${physics_detail.matched_route_name}<br>` +
      `${best.activity_name} · ${best.activity_date} · ${_fmtDuration(best.duration_sec)}`;
  } else {
    document.getElementById('ftpPhysVal').textContent = '—';
    document.getElementById('ftpPhysBasis').textContent = '選擇活動與路段後點擊逆推';
  }
}

// ── 完整卡片渲染 ─────────────────────────────────────────────────────────

function _renderCard(data) {
  _ftpSuggestData = data;
  _hideError();

  const applied = (data.delta === 0);

  _updateBadge(data);
  _renderMmp(data);
  _renderPhysicsResult(data.ftp_physics, data.physics_detail);

  if (applied) {
    _renderValuesC(data);
    _showState('C');
  } else {
    _renderValuesB(data);
    _showState('B');
  }

  if (data.generated_at) {
    const ts = document.getElementById('ftpSuggestTimestamp');
    ts.textContent = data.generated_at;
    ts.classList.remove('hidden');
  }
}

// ── Loading 狀態 ─────────────────────────────────────────────────────────

function _setLoading(loading) {
  const btn     = document.getElementById('ftpSuggestBtn');
  const spinner = document.getElementById('ftpSuggestSpinner');
  const label   = document.getElementById('ftpSuggestBtnLabel');
  btn.disabled = loading;
  spinner.classList.toggle('hidden', !loading);
  if (loading) label.textContent = '估算中…';
}

// ── 收合 / 展開 ──────────────────────────────────────────────────────────

function ftpSuggestToggle() {
  const panel   = document.getElementById('ftpSuggestPanel');
  const chevron = document.getElementById('ftpSuggestChevron');
  const open    = panel.classList.toggle('hidden');
  chevron.style.transform = open ? '' : 'rotate(180deg)';
}

// ── 物理逆推 ─────────────────────────────────────────────────────────────

function _updatePhysRunBtn() {
  const actVal   = document.getElementById('ftpPhysActivitySelect').value;
  const routeVal = document.getElementById('ftpPhysRouteSelect').value;
  document.getElementById('ftpPhysRunBtn').disabled = !(actVal && routeVal);
}

async function _loadPhysicsSelects() {
  try {
    const [actsRes, routesRes] = await Promise.all([
      fetch('/api/activities-with-power'),
      fetch('/api/routes'),
    ]);
    const acts   = await actsRes.json();
    const routes = await routesRes.json();

    const actSel   = document.getElementById('ftpPhysActivitySelect');
    const routeSel = document.getElementById('ftpPhysRouteSelect');

    actSel.innerHTML   = '<option value="">選擇活動…</option>';
    routeSel.innerHTML = '<option value="">選擇路段…</option>';

    if (Array.isArray(acts)) {
      acts.forEach(a => {
        const opt = document.createElement('option');
        opt.value = a.id;
        const mins = Math.floor(a.moving_time / 60);
        opt.textContent = `${a.date} ${a.name} (${mins}min, ↑${a.elevation_m}m)`;
        actSel.appendChild(opt);
      });
    }

    if (Array.isArray(routes)) {
      routes.forEach(r => {
        const opt = document.createElement('option');
        opt.value = r.id;
        opt.textContent = `${r.name} (${r.distance_km}km, ↑${r.elevation_m}m)`;
        routeSel.appendChild(opt);
      });
    }

    actSel.addEventListener('change', _updatePhysRunBtn);
    routeSel.addEventListener('change', _updatePhysRunBtn);
  } catch (err) {
    console.error('[FTP] 選單載入失敗:', err);
  }
}

async function ftpPhysicsRun() {
  const activity_id = parseInt(document.getElementById('ftpPhysActivitySelect').value);
  const route_id    = document.getElementById('ftpPhysRouteSelect').value;
  if (!activity_id || !route_id) return;

  const btn     = document.getElementById('ftpPhysRunBtn');
  const spinner = document.getElementById('ftpPhysSpinner');
  const label   = document.getElementById('ftpPhysRunLabel');
  btn.disabled = true;
  spinner.classList.remove('hidden');
  label.textContent = '逆推中…';

  try {
    const res  = await fetch('/api/ftp-physics', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ activity_id, route_id }),
    });
    const data = await res.json();

    if (res.ok && data.ftp_physics) {
      _renderPhysicsResult(data.ftp_physics, data.physics_detail);

      if (_ftpSuggestData) {
        const ftp_mmp = _ftpSuggestData.ftp_mmp;
        _ftpSuggestData.ftp_physics    = data.ftp_physics;
        _ftpSuggestData.physics_detail = data.physics_detail;

        if (ftp_mmp) {
          _ftpSuggestData.ftp_final = Math.round(ftp_mmp * 0.60 + data.ftp_physics * 0.40);
          _ftpSuggestData.weights   = { mmp: 0.60, physics: 0.40 };
        } else {
          _ftpSuggestData.ftp_final = data.ftp_physics;
        }
        _ftpSuggestData.delta = _ftpSuggestData.ftp_final - _ftpSuggestData.ftp_current;

        // 重新渲染主值（可能從 C 變回 B）
        const applied = _ftpSuggestData.delta === 0;
        if (applied) {
          _renderValuesC(_ftpSuggestData);
          _showState('C');
        } else {
          _renderValuesB(_ftpSuggestData);
          _showState('B');
        }
        _updateBadge(_ftpSuggestData);
      }
    } else {
      document.getElementById('ftpPhysBasis').textContent = data.error || '逆推失敗，請重試。';
    }
  } catch (_) {
    document.getElementById('ftpPhysBasis').textContent = '網路錯誤，請重試。';
  } finally {
    btn.disabled = false;
    spinner.classList.add('hidden');
    label.textContent = '逆推';
    _updatePhysRunBtn();
  }
}

// ── 估算 FTP ─────────────────────────────────────────────────────────────

async function ftpSuggestRun() {
  _setLoading(true);
  _hideError();
  try {
    const res  = await fetch('/api/ftp-suggest', { method: 'POST' });
    const data = await res.json();
    if (res.ok && data.ok) {
      _renderCard(data);
    } else {
      _renderValuesNoData();
      _showState('nodata');
      if (data.error) _showError(data.error);
    }
  } catch (_) {
    _showError('網路錯誤，請重試。');
  } finally {
    _setLoading(false);
  }
}

// ── 套用建議 FTP ─────────────────────────────────────────────────────────

async function ftpSuggestApply() {
  if (!_ftpSuggestData) return;
  const ftp = _ftpSuggestData.ftp_final;
  if (!ftp) return;

  const btn = document.getElementById('ftpApplyBtn');
  btn.disabled    = true;
  btn.textContent = '套用中…';

  try {
    const res = await fetch('/api/profile', {
      method:  'PUT',
      headers: { 'Content-Type': 'application/json' },
      body:    JSON.stringify({ ftp_watts: ftp }),
    });

    if (res.ok) {
      _ftpSuggestData.ftp_current = ftp;
      _ftpSuggestData.delta       = 0;
      _renderValuesC(_ftpSuggestData);
      _showState('C');
      _updateBadge(_ftpSuggestData);
    } else {
      btn.disabled    = false;
      btn.textContent = '套用建議值';
      _showError('套用失敗，請重試。');
    }
  } catch (_) {
    btn.disabled    = false;
    btn.textContent = '套用建議值';
    _showError('網路錯誤，請重試。');
  }
}

// ── 複製給 AI（Markdown）────────────────────────────────────────────────

async function ftpSuggestCopy() {
  if (!_ftpSuggestData) return;
  const d = _ftpSuggestData;

  let profileData = null;
  try {
    profileData = await fetch('/api/profile').then(r => r.json());
  } catch (_) {}

  const mmpLine = d.ftp_mmp && d.mmp_detail
    ? `| MMP 近似 | ${d.ftp_mmp} W | 基於「${d.mmp_detail.basis_activity_name}」(時長 ${_fmtDuration(d.mmp_detail.basis_duration_sec)}, NP ${d.mmp_detail.basis_np} W, 係數 × ${d.mmp_detail.coeff}) |`
    : '| MMP 近似 | — | 無足夠資料 |';

  const physLine = d.ftp_physics && d.physics_detail
    ? (() => {
        const best = d.physics_detail.basis_activities[0];
        return `| 物理逆推 | ${d.ftp_physics} W | 路段「${d.physics_detail.matched_route_name}」，活動「${best.activity_name}」完賽 ${_fmtDuration(best.duration_sec)} |`;
      })()
    : '| 物理逆推 | — | 尚未逆推 |';

  const weightLine = d.weights
    ? `MMP × ${Math.round(d.weights.mmp * 100)}% + 物理逆推 × ${Math.round(d.weights.physics * 100)}%`
    : 'MMP × 100%（無物理逆推資料）';

  const wPerKg        = (d.weight_kg && d.ftp_final)   ? (d.ftp_final   / d.weight_kg).toFixed(2) : '—';
  const currentWPerKg = (d.weight_kg && d.ftp_current) ? (d.ftp_current / d.weight_kg).toFixed(2) : '—';
  const tsb           = d.tsb ?? 0;
  const tsbStatus     = tsb > 5 ? '狀態良好' : tsb > 0 ? '輕微疲勞' : tsb > -10 ? '中度疲勞' : '過度訓練';

  let mmpSection = '尚無資料';
  if (d.mmp_detail) {
    const m = d.mmp_detail;
    mmpSection = [
      `- **活動名稱**：${m.basis_activity_name}`,
      `- **日期**：${m.basis_date}`,
      `- **時長**：${_fmtDuration(m.basis_duration_sec)}`,
      `- **NP**：${m.basis_np} W`,
      `- **換算係數**：× ${m.coeff}`,
      `- **推算 FTP**：${d.ftp_mmp} W`,
    ].join('\n');
  }

  let physSection = '尚未進行物理逆推';
  if (d.physics_detail) {
    const pd   = d.physics_detail;
    const best = pd.basis_activities[0];
    physSection = [
      `- **路段**：${pd.matched_route_name}`,
      `- **活動名稱**：${best.activity_name}`,
      `- **日期**：${best.activity_date}`,
      `- **完賽時間**：${_fmtDuration(best.duration_sec)}`,
      `- **逆推 FTP**：${best.req_ftp} W`,
      `- **條件**：騎手 ${d.weight_kg} kg + 車重 ${d.bike_weight_kg} kg，TSB ${d.tsb}`,
    ].join('\n');
  }

  const report = `## VeloData FTP 估算報告
生成時間：${d.generated_at ?? '—'}

---

### 估算結果摘要

| 模型 | FTP 估算值 | 說明 |
|------|-----------|------|
${mmpLine}
${physLine}
| **加權建議值** | **${d.ftp_final} W** | ${weightLine} |

與目前設定差值：${d.delta >= 0 ? '+' : ''}${d.delta} W（目前 ${d.ftp_current} W → 建議 ${d.ftp_final} W）

---

### 運動員資料

| 項目 | 數值 |
|------|------|
| 騎手體重 | ${d.weight_kg} kg |
| 車重 | ${d.bike_weight_kg} kg |
| 目前 FTP | ${d.ftp_current} W（${currentWPerKg} W/kg）|
| 建議 FTP | ${d.ftp_final} W（${wPerKg} W/kg）|
| 當前 TSB | ${d.tsb}（${tsbStatus}）|

---

### MMP 近似模型

${mmpSection}

---

### 物理逆推模型

${physSection}

---

### 加權說明

${d.weights && d.weights.physics > 0
  ? `MMP × ${Math.round(d.weights.mmp * 100)}% + 物理逆推 × ${Math.round(d.weights.physics * 100)}%\n最終建議值 = ${d.ftp_mmp} × 0.6 + ${d.ftp_physics} × 0.4 = **${d.ftp_final} W**`
  : `僅 MMP 模型有效，建議進行物理逆推提升精準度。\n最終建議值：**${d.ftp_final} W**`
}`;

  try {
    await navigator.clipboard.writeText(report);
    const label = document.getElementById('ftpCopyBtnLabel');
    label.textContent = '已複製！';
    setTimeout(() => { label.textContent = '複製給 AI'; }, 2000);
  } catch (_) {
    _showError('複製失敗，請手動選取。');
  }
}

// ── 初始化 ───────────────────────────────────────────────────────────────

async function ftpSuggestInit() {
  await _loadPhysicsSelects();
  try {
    const res  = await fetch('/api/ftp-suggest');
    const data = await res.json();
    if (data && data.ok) {
      _renderCard(data);
    }
    // 若無快取資料，維持預設狀態 A（HTML 已預渲染）
  } catch (_) {
    // 靜默失敗，維持狀態 A
  }
}

if (document.readyState === 'loading') {
  document.addEventListener('DOMContentLoaded', ftpSuggestInit);
} else {
  ftpSuggestInit();
}
