const ACT_PAGE_SIZE = 9;
let actCurrentPage = 1;
let actSortedCards = [];

const actGrid = document.getElementById('actGrid');

function actApplySort() {
  const sort = document.getElementById('actSortSelect').value;
  const cards = Array.from(document.querySelectorAll('.act-card'));

  const key = {
    date_desc:     c => -parseFloat(c.dataset.ts),
    date_asc:      c =>  parseFloat(c.dataset.ts),
    watts_desc:    c => -parseFloat(c.dataset.watts),
    speed_desc:    c => -parseFloat(c.dataset.speed),
    distance_desc: c => -parseFloat(c.dataset.distance),
    tss_desc:      c => -parseFloat(c.dataset.tss),
  }[sort] || (c => -parseFloat(c.dataset.ts));

  actSortedCards = cards.sort((a, b) => key(a) - key(b));
  actSortedCards.forEach(c => actGrid.appendChild(c));
  actChangePage(1);
}

function actChangePage(page) {
  const total = actSortedCards.length;
  const totalPages = Math.max(1, Math.ceil(total / ACT_PAGE_SIZE));
  if (page < 1 || page > totalPages) return;
  actCurrentPage = page;
  const start = (page - 1) * ACT_PAGE_SIZE;
  const end = start + ACT_PAGE_SIZE;
  actSortedCards.forEach((card, i) => {
    card.classList.toggle('hidden', i < start || i >= end);
  });
  document.getElementById('actPageLabel').textContent = `第 ${page} / ${totalPages} 頁`;
  document.getElementById('actPageInfo').textContent = `共 ${total} 筆`;
  document.getElementById('actPrevBtn').disabled = page <= 1;
  document.getElementById('actNextBtn').disabled = page >= totalPages;
  document.getElementById('actPagination').style.display = totalPages <= 1 ? 'none' : 'flex';
}

actApplySort();
