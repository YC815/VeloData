/* FTP 估算卡片邏輯 */

let _ftpSuggestData = null;

function _fmtDuration(sec) {
  const m = Math.floor(sec / 60);
  const s = sec % 60;
  return `${m}:${String(s).padStart(2, '0')}`;
}

function _updateMainValues() {
  if (!_ftpSuggestData) return;
  const d = _ftpSuggestData;

  document.getElementById('ftpCurrentVal').textContent = d.ftp_current ?? '—';
  document.getElementById('ftpFinalVal').textContent = d.ftp_final ?? '—';

  const deltaEl = document.getElementById('ftpDeltaVal');
  const delta = d.delta ?? 0;
  if (delta > 0) {
    deltaEl.textContent = `+${delta}`;
    deltaEl.className = 'text-2xl font-mono font-bold text-green-400';
  } else if (delta < 0) {
    deltaEl.textContent = String(delta);
    deltaEl.className = 'text-2xl font-mono font-bold text-red-400';
  } else {
    deltaEl.textContent = '±0';
    deltaEl.className = 'text-2xl font-mono font-bold text-slate-400';
  }
}

function _updateBadge(data) {
  const badge = document.getElementById('ftpSuggestBadge');
  const ts = document.getElementById('ftpSuggestTimestamp');
  const wkg = document.getElementById('ftpWperKgBadge');
  if (!data) {
    badge.textContent = '尚未估算';
    ts.textContent = '';
    wkg.classList.add('hidden');
    return;
  }
  const deltaStr = data.delta > 0
    ? ` <span class="text-green-400">▲+${data.delta}W</span>`
    : data.delta < 0
    ? ` <span class="text-red-400">▼${data.delta}W</span>`
    : '';
  badge.innerHTML = `目前 FTP <span class="text-orange-300 font-bold">${data.ftp_current} W</span>${deltaStr}`;
  if (data.weight_kg && data.ftp_current) {
    wkg.textContent = `${(data.ftp_current / data.weight_kg).toFixed(2)} W/kg`;
    wkg.classList.remove('hidden');
  }
  if (data.generated_at) {
    ts.textContent = data.generated_at;
    ts.classList.remove('hidden');
  }
}

function _renderCard(data) {
  _ftpSuggestData = data;

  document.getElementById('ftpSuggestResult').classList.remove('hidden');
  document.getElementById('ftpSuggestEmpty').classList.add('hidden');

  _updateBadge(data);
  _updateMainValues();

  // MMP 子模型
  if (data.ftp_mmp && data.mmp_detail) {
    const d = data.mmp_detail;
    document.getElementById('ftpMmpVal').textContent = `${data.ftp_mmp} W`;
    document.getElementById('ftpMmpBasis').innerHTML =
      `${d.basis_activity_name}<br>` +
      `${d.basis_date}・時長 ${_fmtDuration(d.basis_duration_sec)}・NP ${d.basis_np} W` +
      `<br>係數 × ${d.coeff}`;
  } else {
    document.getElementById('ftpMmpVal').textContent = '—';
    document.getElementById('ftpMmpBasis').textContent = '無足夠資料';
  }

  // 物理逆推結果（若有）
  _renderPhysicsResult(data.ftp_physics, data.physics_detail);

  // 時間戳
  if (data.generated_at) {
    document.getElementById('ftpSuggestTimestamp').textContent = `${data.generated_at} 生成`;
  }

  // 若 delta 為 0（已套用過），隱藏建議 FTP 和差值欄位，套用按鈕改為已套用
  const applied = (data.delta === 0);
  document.getElementById('ftpFinalCell').classList.toggle('hidden', applied);
  document.getElementById('ftpDeltaCell').classList.toggle('hidden', applied);
  const applyBtn = document.getElementById('ftpApplyBtn');
  applyBtn.disabled = applied;
  applyBtn.textContent = applied ? '已套用' : '套用建議值';
  if (!applied) applyBtn.disabled = false;
  document.getElementById('ftpCopyBtn').disabled = false;
  document.getElementById('ftpSuggestBtnLabel').textContent = '重新運算';
}

function _renderPhysicsResult(ftp_physics, physics_detail) {
  if (ftp_physics && physics_detail) {
    const best = physics_detail.basis_activities[0];
    document.getElementById('ftpPhysVal').textContent = `${ftp_physics} W`;
    document.getElementById('ftpPhysBasis').innerHTML =
      `${physics_detail.matched_route_name}<br>` +
      `${best.activity_name}・${best.activity_date}` +
      `・完賽 ${_fmtDuration(best.duration_sec)}`;
  } else {
    document.getElementById('ftpPhysVal').textContent = '—';
    document.getElementById('ftpPhysBasis').textContent = '尚未逆推，請選擇活動與路段';
  }
}

function _renderError(msg) {
  document.getElementById('ftpSuggestResult').classList.add('hidden');
  document.getElementById('ftpSuggestEmpty').classList.remove('hidden');
  document.getElementById('ftpSuggestEmpty').textContent = msg || '估算失敗，請稍後再試。';
}

function _setLoading(loading) {
  const btn = document.getElementById('ftpSuggestBtn');
  const spinner = document.getElementById('ftpSuggestSpinner');
  const label = document.getElementById('ftpSuggestBtnLabel');
  btn.disabled = loading;
  spinner.classList.toggle('hidden', !loading);
  if (loading) label.textContent = '估算中…';
}

// ── 選單：活動 + 路段 ────────────────────────────────────────────────────

function ftpSuggestToggle() {
  const panel = document.getElementById('ftpSuggestPanel');
  const chevron = document.getElementById('ftpSuggestChevron');
  const open = panel.classList.toggle('hidden');
  chevron.style.transform = open ? '' : 'rotate(180deg)';
}

function ftpPhysToggle() {
  const panel = document.getElementById('ftpPhysPanel');
  panel.classList.toggle('hidden');
}

function _updatePhysRunBtn() {
  const actVal = document.getElementById('ftpPhysActivitySelect').value;
  const routeVal = document.getElementById('ftpPhysRouteSelect').value;
  document.getElementById('ftpPhysRunBtn').disabled = !(actVal && routeVal);
}

async function _loadPhysicsSelects() {
  try {
    const [actsRes, routesRes] = await Promise.all([
      fetch('/api/activities-with-power'),
      fetch('/api/routes'),
    ]);
    const acts = await actsRes.json();
    const routes = await routesRes.json();

    const actSel = document.getElementById('ftpPhysActivitySelect');
    const routeSel = document.getElementById('ftpPhysRouteSelect');

    // 清空避免重複填入（HTMX 換頁後 init 可能重跑）
    actSel.innerHTML = '<option value="">選擇活動…</option>';
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

// ── 物理逆推觸發 ─────────────────────────────────────────────────────────

async function ftpPhysicsRun() {
  const activity_id = parseInt(document.getElementById('ftpPhysActivitySelect').value);
  const route_id = document.getElementById('ftpPhysRouteSelect').value;
  if (!activity_id || !route_id) return;

  const btn = document.getElementById('ftpPhysRunBtn');
  const spinner = document.getElementById('ftpPhysSpinner');
  const label = document.getElementById('ftpPhysRunLabel');
  btn.disabled = true;
  spinner.classList.remove('hidden');
  label.textContent = '逆推中…';

  try {
    const res = await fetch('/api/ftp-physics', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ activity_id, route_id }),
    });
    const data = await res.json();

    if (res.ok && data.ftp_physics) {
      _renderPhysicsResult(data.ftp_physics, data.physics_detail);

      // 更新主卡片加權結果
      if (_ftpSuggestData) {
        const ftp_mmp = _ftpSuggestData.ftp_mmp;
        if (ftp_mmp) {
          _ftpSuggestData.ftp_physics = data.ftp_physics;
          _ftpSuggestData.physics_detail = data.physics_detail;
          _ftpSuggestData.ftp_final = Math.round(ftp_mmp * 0.60 + data.ftp_physics * 0.40);
          _ftpSuggestData.delta = _ftpSuggestData.ftp_final - _ftpSuggestData.ftp_current;
          _ftpSuggestData.weights = { mmp: 0.60, physics: 0.40 };
        } else {
          _ftpSuggestData.ftp_physics = data.ftp_physics;
          _ftpSuggestData.physics_detail = data.physics_detail;
          _ftpSuggestData.ftp_final = data.ftp_physics;
          _ftpSuggestData.delta = _ftpSuggestData.ftp_final - _ftpSuggestData.ftp_current;
        }
        _updateMainValues();
        document.getElementById('ftpApplyBtn').disabled = false;
        document.getElementById('ftpCopyBtn').disabled = false;
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
    // 逆推完成後收起 panel
    document.getElementById('ftpPhysPanel').classList.add('hidden');
  }
}

// ── 頁面載入 ─────────────────────────────────────────────────────────────

async function ftpSuggestInit() {
  await _loadPhysicsSelects();
  try {
    const res = await fetch('/api/ftp-suggest');
    const data = await res.json();
    if (data && data.ok) {
      _renderCard(data);
    }
  } catch (_) {
    // 靜默失敗
  }
}

// ── 估算 / 重新運算 ──────────────────────────────────────────────────────

async function ftpSuggestRun() {
  _setLoading(true);
  try {
    const res = await fetch('/api/ftp-suggest', { method: 'POST' });
    const data = await res.json();
    if (res.ok && data.ok) {
      _renderCard(data);
    } else {
      _renderError(data.error);
    }
  } catch (_) {
    _renderError('網路錯誤，請重試。');
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
  btn.disabled = true;
  btn.textContent = '套用中…';

  try {
    const res = await fetch('/api/profile', {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ ftp_watts: ftp }),
    });
    if (res.ok) {
      // 更新「目前 FTP」顯示為新值，隱藏「建議 FTP」和「差值」欄位
      document.getElementById('ftpCurrentVal').textContent = ftp;
      document.getElementById('ftpFinalCell').classList.add('hidden');
      document.getElementById('ftpDeltaCell').classList.add('hidden');
      btn.textContent = '已套用';
      if (_ftpSuggestData) {
        _ftpSuggestData.ftp_current = ftp;
        _ftpSuggestData.delta = 0;
        _updateBadge(_ftpSuggestData);
        _updateMainValues();
      }
    } else {
      btn.disabled = false;
      btn.textContent = '套用建議值';
      alert('套用失敗，請重試。');
    }
  } catch (_) {
    btn.disabled = false;
    btn.textContent = '套用建議值';
    alert('網路錯誤，請重試。');
  }
}

// ── 複製給 AI（Markdown）────────────────────────────────────────────────

async function ftpSuggestCopy() {
  if (!_ftpSuggestData) return;
  const d = _ftpSuggestData;

  // 同時拉取補充數據（PMC、本週、武嶺預測）
  let pmcData = null;
  let profileData = null;
  try {
    const [pmcRes, profileRes] = await Promise.all([
      fetch('/api/ftp-suggest'),   // 快取已含 tsb/weight
      fetch('/api/profile'),
    ]);
    pmcData = await pmcRes.json();
    profileData = await profileRes.json();
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

  const wPerKg = (d.weight_kg && d.ftp_final)
    ? (d.ftp_final / d.weight_kg).toFixed(2)
    : '—';
  const currentWPerKg = (d.weight_kg && d.ftp_current)
    ? (d.ftp_current / d.weight_kg).toFixed(2)
    : '—';

  // MMP 採用活動詳細
  let mmpSection = '尚無資料';
  if (d.mmp_detail) {
    const m = d.mmp_detail;
    const avgW = m.basis_np ? Math.round(m.basis_np / (m.coeff || 1)) : '—';
    mmpSection = [
      `- **活動名稱**：${m.basis_activity_name}`,
      `- **日期**：${m.basis_date}`,
      `- **時長（moving time）**：${_fmtDuration(m.basis_duration_sec)}`,
      `- **NP（標準化功率）**：${m.basis_np} W`,
      `- **換算係數**：× ${m.coeff}（${m.basis_duration_sec <= 1350 ? '≤22.5min，視為 20min 全力測驗' : '>22.5min，視為 30min 全力測驗'}）`,
      `- **推算 FTP**：${m.ftp_mmp} W`,
    ].join('\n');
  }

  // 物理逆推採用活動詳細
  let physSection = '尚未進行物理逆推';
  if (d.physics_detail) {
    const pd = d.physics_detail;
    const best = pd.basis_activities[0];
    physSection = [
      `- **路段**：${pd.matched_route_name}`,
      `- **活動名稱**：${best.activity_name}`,
      `- **日期**：${best.activity_date}`,
      `- **路段完賽時間（elapsed_time）**：${_fmtDuration(best.duration_sec)}`,
      `- **逆推 FTP**：${best.req_ftp} W`,
      `- **計算說明**：輸入完賽時間 ${_fmtDuration(best.duration_sec)} 至物理模型二分搜尋，` +
        `在相同體重（${d.weight_kg} kg 騎手 + ${d.bike_weight_kg} kg 車重）` +
        `與 TSB ${d.tsb} 條件下，逆推出能跑出該時間所需的最低 FTP`,
    ].join('\n');
    if (pd.basis_activities.length > 1) {
      physSection += `\n- **其他參考活動**：共 ${pd.basis_activities.length} 筆，取中位數`;
    }
  }

  // TSB 狀態文字
  const tsb = d.tsb ?? 0;
  const tsbStatus = tsb > 5 ? '狀態良好' : tsb > 0 ? '輕微疲勞' : tsb > -10 ? '中度疲勞' : '過度訓練';

  const report = `## VeloData FTP 估算報告
生成時間：${d.generated_at ?? '—'}

---

### 一、估算結果摘要

| 模型 | FTP 估算值 | 說明 |
|------|-----------|------|
${mmpLine}
${physLine}
| **加權建議值** | **${d.ftp_final} W** | ${weightLine} |

**與目前設定差值：${d.delta >= 0 ? '+' : ''}${d.delta} W**（目前 ${d.ftp_current} W → 建議 ${d.ftp_final} W）

---

### 二、運動員資料

| 項目 | 數值 |
|------|------|
| 騎手體重 | ${d.weight_kg} kg |
| 車重 | ${d.bike_weight_kg} kg |
| 系統總重 | ${(d.weight_kg + d.bike_weight_kg).toFixed(1)} kg |
| 目前 FTP | ${d.ftp_current} W（${currentWPerKg} W/kg）|
| 建議 FTP | ${d.ftp_final} W（${wPerKg} W/kg）|
| 當前 TSB | ${d.tsb}（${tsbStatus}）|

---

### 三、MMP 近似模型詳細

${mmpSection}

**計算方式說明**：從近 90 天有功率計的騎乘中，篩選持續時間 15–40 分鐘的活動，取最高 NP（標準化功率），依完賽時長套用換算係數（20min × 0.95、30min × 0.97）推算 FTP。

---

### 四、物理逆推模型詳細

${physSection}

**計算方式說明**：物理模型考慮重力（坡度 × 體重）、風阻（CdA × 空氣密度 × 速度²）、滾動阻力（Crr × 體重）三大阻力，在給定完賽時間的約束下，以二分搜尋法逆推出能剛好跑出該時間所需的功率輸出，再依強度係數（IF）換算為 FTP 估算值。

---

### 五、加權說明

${d.weights && d.weights.physics > 0
  ? `兩個模型均有有效結果，採用加權合成：\n- MMP 近似 × ${Math.round(d.weights.mmp * 100)}%（生理測驗為主）\n- 物理逆推 × ${Math.round(d.weights.physics * 100)}%（實際路段成績校驗）\n\n最終建議值 = ${d.ftp_mmp} × 0.6 + ${d.ftp_physics} × 0.4 = **${d.ftp_final} W**`
  : `本次僅有 MMP 近似模型有效結果，建議進行物理逆推以提升精準度。\n最終建議值直接採用 MMP 結果：**${d.ftp_final} W**`
}`;

  try {
    await navigator.clipboard.writeText(report);
    const label = document.getElementById('ftpCopyBtnLabel');
    label.textContent = '已複製！';
    setTimeout(() => { label.textContent = '複製給 AI'; }, 2000);
  } catch (_) {
    alert('複製失敗，請手動選取。');
  }
}

if (document.readyState === 'loading') {
  document.addEventListener('DOMContentLoaded', ftpSuggestInit);
} else {
  ftpSuggestInit();
}
