let _exportData = null;

async function preloadExportData() {
  try {
    const res = await fetch('/api/export-for-ai');
    if (!res.ok) return;
    _exportData = await res.json();
  } catch (_) {
    // 靜默失敗，點擊時再 fetch
  }
}

function formatExportText(d) {
  const lines = [];
  lines.push('# VeloData 訓練摘要');
  lines.push(`產生時間：${d.generated_at}`);
  lines.push('');

  lines.push('## 個人檔案');
  lines.push(`姓名：${d.athlete.name}`);
  lines.push(`FTP：${d.athlete.ftp_watts} W`);
  if (d.athlete.weight_kg) lines.push(`體重：${d.athlete.weight_kg} kg`);
  if (d.athlete.w_per_kg) lines.push(`W/kg：${d.athlete.w_per_kg}`);
  lines.push('');

  lines.push('## 當前健身狀態（PMC）');
  lines.push(`CTL（慢性訓練負荷）：${d.current_fitness.ctl}`);
  lines.push(`ATL（急性訓練負荷）：${d.current_fitness.atl}`);
  lines.push(`TSB（訓練壓力餘額）：${d.current_fitness.tsb}`);
  lines.push(`狀態評估：${d.current_fitness.status}`);
  lines.push('');

  lines.push('## 本週統計');
  lines.push(`TSS：${d.this_week.tss}`);
  lines.push(`距離：${d.this_week.distance_km} km`);
  lines.push(`時間：${d.this_week.time}`);
  lines.push('');

  if (d.wuling_prediction.current_time !== '—') {
    lines.push('## 西進武嶺預測');
    lines.push(`當下狀態預測時間：${d.wuling_prediction.current_time}`);
    lines.push(`充分休息後預測時間：${d.wuling_prediction.ideal_time}`);
    if (d.wuling_prediction.delta_mins > 0) {
      lines.push(`差距：休息後可省 ${d.wuling_prediction.delta_mins} 分鐘`);
    }
    lines.push('');
  }

  lines.push('## 最近 10 筆騎乘');
  for (const act of d.recent_activities) {
    lines.push(`### ${act.date} ${act.name}`);
    const stats = [];
    if (act.distance_km) stats.push(`距離 ${act.distance_km} km`);
    stats.push(`時間 ${act.duration}`);
    if (act.elevation_m > 0) stats.push(`爬升 ${act.elevation_m} m`);
    if (act.avg_speed_kmh) stats.push(`均速 ${act.avg_speed_kmh} km/h`);
    if (act.avg_watts) stats.push(`均瓦 ${act.avg_watts} W`);
    if (act.weighted_watts) stats.push(`加權瓦 ${act.weighted_watts} W`);
    if (act.avg_hr) stats.push(`均心率 ${act.avg_hr} bpm`);
    if (act.avg_cadence) stats.push(`踏頻 ${act.avg_cadence} rpm`);
    if (act.tss) stats.push(`TSS ${act.tss}`);
    if (act.if_value) stats.push(`IF ${act.if_value}`);
    lines.push(stats.join(' · '));
    if (act.interpretation) lines.push(`強度解讀：${act.interpretation}`);
    if (act.recovery_note) lines.push(`恢復建議：${act.recovery_note}`);
    lines.push('');
  }

  return lines.join('\n');
}

async function copyForAI() {
  const btn = document.getElementById('copyAiBtn');
  const label = document.getElementById('copyAiLabel');
  const icon = document.getElementById('copyAiIcon');

  btn.disabled = true;

  try {
    let d = _exportData;
    if (!d) {
      label.textContent = '載入中...';
      const res = await fetch('/api/export-for-ai');
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      d = await res.json();
      _exportData = d;
    }

    await navigator.clipboard.writeText(formatExportText(d));

    icon.innerHTML = '<path stroke-linecap="round" stroke-linejoin="round" d="M5 13l4 4L19 7"/>';
    label.textContent = '已複製！';
    btn.classList.remove('text-slate-300', 'hover:text-orange-300');
    btn.classList.add('text-green-400');

    setTimeout(() => {
      icon.innerHTML = '<path stroke-linecap="round" stroke-linejoin="round" d="M8 16H6a2 2 0 01-2-2V6a2 2 0 012-2h8a2 2 0 012 2v2m-6 12h8a2 2 0 002-2v-8a2 2 0 00-2-2h-8a2 2 0 00-2 2v8a2 2 0 002 2z"/>';
      label.textContent = '複製訓練摘要';
      btn.classList.add('text-slate-300', 'hover:text-orange-300');
      btn.classList.remove('text-green-400');
      btn.disabled = false;
    }, 2000);

  } catch (err) {
    label.textContent = '複製失敗';
    btn.classList.add('text-red-400');
    setTimeout(() => {
      label.textContent = '複製訓練摘要';
      btn.classList.remove('text-red-400');
      btn.disabled = false;
    }, 2000);
    console.error('copyForAI error:', err);
  }
}

document.addEventListener('DOMContentLoaded', () => {
  setTimeout(preloadExportData, 1000);
});
