function togglePmcLegend() {
  const legend = document.getElementById('pmcLegend');
  const label = document.getElementById('pmcLegendLabel');
  const isHidden = legend.classList.toggle('hidden');
  label.textContent = isHidden ? '圖說' : '收合';
}

function openSettings() {
  document.getElementById('settingsModal').classList.remove('hidden');
  document.getElementById('saveMsg').classList.add('hidden');
  document.getElementById('saveErr').classList.add('hidden');
}

function closeSettings() {
  document.getElementById('settingsModal').classList.add('hidden');
}

document.addEventListener('keydown', e => {
  if (e.key === 'Escape') closeSettings();
});

async function saveSettings() {
  const btn = document.getElementById('saveBtn');
  const msg = document.getElementById('saveMsg');
  const err = document.getElementById('saveErr');
  msg.classList.add('hidden');
  err.classList.add('hidden');

  const ftp = parseInt(document.getElementById('ftpInput').value);
  const weight = parseFloat(document.getElementById('weightInput').value);
  const timezone = document.getElementById('timezoneSelect').value;

  if (!ftp || ftp <= 0 || ftp > 600) {
    err.textContent = 'FTP 請輸入 1–600 之間的數值';
    err.classList.remove('hidden');
    return;
  }
  if (!weight || weight <= 0 || weight > 200) {
    err.textContent = '體重請輸入 1–200 之間的數值';
    err.classList.remove('hidden');
    return;
  }

  btn.disabled = true;
  btn.textContent = '儲存中…';
  try {
    const res = await fetch('/api/profile', {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ ftp_watts: ftp, weight_kg: weight, timezone }),
    });
    if (!res.ok) {
      const data = await res.json();
      throw new Error(data.error || '儲存失敗');
    }
    msg.classList.remove('hidden');
    setTimeout(() => location.reload(), 900);
  } catch (e) {
    err.textContent = e.message;
    err.classList.remove('hidden');
  } finally {
    btn.disabled = false;
    btn.textContent = '儲存';
  }
}
