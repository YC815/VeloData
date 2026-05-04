Chart.register({
  id: 'tsbLegendGradient',
  afterDraw(chart) {
    const legend = chart.legend;
    if (!legend) return;
    (legend.legendItems || []).forEach((item, i) => {
      if (item.text !== 'TSB') return;
      const box = (legend.legendHitBoxes || [])[i];
      if (!box) return;
      const c = chart.ctx;
      const bw = 20; // matches legend boxWidth
      const bh = 10;
      const x = box.left;
      const cy = box.top + box.height / 2;

      c.save();

      // Left half fill (red, x <= 0)
      c.fillStyle = 'rgba(248, 113, 113, 0.4)';
      c.fillRect(x, cy - bh / 2, bw / 2, bh);
      // Right half fill (green, x > 0)
      c.fillStyle = 'rgba(74, 222, 128, 0.4)';
      c.fillRect(x + bw / 2, cy - bh / 2, bw / 2, bh);

      // Left dashed line (red)
      c.strokeStyle = 'rgba(248, 113, 113, 0.9)';
      c.lineWidth = 1.5;
      c.setLineDash([4, 4]);
      c.lineDashOffset = 0;
      c.beginPath();
      c.moveTo(x, cy);
      c.lineTo(x + bw / 2, cy);
      c.stroke();
      // Right dashed line (green) — offset continues the dash rhythm
      c.strokeStyle = 'rgba(74, 222, 128, 0.9)';
      c.lineDashOffset = (bw / 2) % 8;
      c.beginPath();
      c.moveTo(x + bw / 2, cy);
      c.lineTo(x + bw, cy);
      c.stroke();

      c.restore();
    });
  },
});

function initPmcChart() {
  const existing = Chart.getChart('pmcChart');
  if (existing) existing.destroy();

  const pmcData = JSON.parse(document.getElementById('pmcData').textContent);
  const ctx = document.getElementById('pmcChart').getContext('2d');

  new Chart(ctx, {
    type: 'line',
    data: {
      labels: pmcData.labels,
      datasets: [
        {
          label: 'CTL',
          data: pmcData.ctl,
          borderColor: 'rgb(34, 211, 238)',
          backgroundColor: 'rgba(34, 211, 238, 0.08)',
          borderWidth: 2,
          pointRadius: 0,
          fill: false,
          tension: 0.3,
        },
        {
          label: 'ATL',
          data: pmcData.atl,
          borderColor: 'rgb(251, 146, 60)',
          backgroundColor: 'rgba(251, 146, 60, 0.08)',
          borderWidth: 2,
          pointRadius: 0,
          fill: false,
          tension: 0.3,
        },
        {
          label: 'TSB',
          data: pmcData.tsb,
          borderColor: (ctx) => {
            const v = ctx.parsed?.y ?? 0;
            return v >= 0 ? 'rgb(74, 222, 128)' : 'rgb(248, 113, 113)';
          },
          segment: {
            borderColor: (ctx) => {
              const y0 = ctx.p0.parsed.y, y1 = ctx.p1.parsed.y;
              return (y0 >= 0 && y1 >= 0) ? 'rgb(74, 222, 128)'
                   : (y0 < 0  && y1 < 0)  ? 'rgb(248, 113, 113)'
                   : 'rgb(200, 200, 200)';
            },
          },
          backgroundColor: (ctx) => {
            const chart = ctx.chart;
            const { ctx: c, chartArea, scales } = chart;
            if (!chartArea) return 'transparent';
            const yZero = scales.y.getPixelForValue(0);
            const top = chartArea.top, bottom = chartArea.bottom;
            const gradPos = Math.max(0, Math.min(1, (yZero - top) / (bottom - top)));
            const grad = c.createLinearGradient(0, top, 0, bottom);
            grad.addColorStop(0,       'rgba(74, 222, 128, 0.18)');
            grad.addColorStop(gradPos, 'rgba(74, 222, 128, 0.04)');
            grad.addColorStop(gradPos, 'rgba(248, 113, 113, 0.04)');
            grad.addColorStop(1,       'rgba(248, 113, 113, 0.18)');
            return grad;
          },
          borderWidth: 1.5,
          borderDash: [4, 4],
          pointRadius: 0,
          fill: 'origin',
          tension: 0.2,
        },
      ],
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      plugins: {
        legend: {
          labels: {
            color: '#a1a1aa',
            font: { size: 11 },
            boxWidth: 20,
            generateLabels(chart) {
              const items = Chart.defaults.plugins.legend.labels.generateLabels(chart);
              return items.map(item => {
                if (item.text === 'TSB') {
                  item.fillStyle = 'transparent';
                  item.strokeStyle = 'transparent';
                  item.lineWidth = 0;
                  item.lineDash = [];
                }
                return item;
              });
            },
          },
        },
        tooltip: {
          mode: 'index',
          intersect: false,
          backgroundColor: '#18181b',
          borderColor: 'rgba(255,255,255,0.1)',
          borderWidth: 1,
          titleColor: '#f4f4f5',
          bodyColor: '#a1a1aa',
        },
      },
      scales: {
        x: {
          ticks: { color: '#71717a', maxTicksLimit: 10, font: { size: 10 } },
          grid: { color: 'rgba(255,255,255,0.05)' },
        },
        y: {
          ticks: { color: '#71717a', font: { size: 10 } },
          grid: { color: 'rgba(255,255,255,0.05)' },
        },
      },
      interaction: { mode: 'nearest', axis: 'x', intersect: false },
    },
  });
}

initPmcChart();

// HTMX 重新 swap 後若有 pmcChart canvas 則重初始化
document.body.addEventListener('htmx:afterSwap', function () {
  if (document.getElementById('pmcChart')) initPmcChart();
});
