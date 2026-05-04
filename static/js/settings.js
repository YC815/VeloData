function togglePmcLegend() {
  const legend = document.getElementById('pmcLegend');
  const label = document.getElementById('pmcLegendLabel');
  const isHidden = legend.classList.toggle('hidden');
  label.textContent = isHidden ? '圖說' : '收合';
}
