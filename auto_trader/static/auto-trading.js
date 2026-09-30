(function () {
  let timer = null;
  let running = false;

  function applyBudget() {
    const percent = document.querySelector('#budget-percent');
    const amount = document.querySelector('#budget-amount');
    const cash = document.querySelector('#cash');
    if (!percent || !amount) return;
    const value = Math.max(1, Math.min(100, Number(percent.value) || 40));
    percent.value = value;
    const balance = Number((cash?.textContent || '').replace(/[^0-9]/g, '')) || 10000000;
    amount.textContent = new Intl.NumberFormat('ko-KR', { style: 'currency', currency: 'KRW', maximumFractionDigits: 0 }).format(balance * value / 100);
  }

  async function run() {
    if (!running) return;
    await fetch('/api/v1/auto-trading/manage', { method: 'POST' });
    const percent = Math.max(1, Math.min(100, Number(document.querySelector('#budget-percent')?.value) || 40));
    const candidates = window.stocks || [];
    const message = document.querySelector('#order-message');
    let filled = 0;
    const reasons = [];
    const selected = candidates.slice().sort((a, b) => Number(b.score || 0) - Number(a.score || 0));
    for (const stock of selected) {
      const response = await fetch(`/api/v1/auto-trading/evaluate?symbol=${stock.symbol}&price=${stock.price}&score=${stock.score || 85}&budget_percent=${percent / Math.max(1, selected.length)}`, { method: 'POST' });
      if (response.ok) { const result = await response.json(); if (result.action === 'BUY') filled += 1; else if (result.reason) reasons.push(`${stock.name}: ${result.reason}`); }
    }
    if (message) message.textContent = filled ? `${filled}개 종목 매수 완료` : `매수 없음: ${reasons.join(' / ') || '조건을 만족한 종목이 없습니다.'}`;
    if (typeof window.refresh === 'function') await window.refresh();
    timer = setTimeout(run, 180000);
  }

  function stop() {
    running = false;
    clearTimeout(timer);
    document.querySelector('#auto-btn').textContent = '자동매매 시작';
  }

  document.addEventListener('DOMContentLoaded', () => {
    const budgetButton = document.querySelector('#budget-apply');
    const budgetInput = document.querySelector('#budget-percent');
    if (budgetButton) budgetButton.onclick = applyBudget;
    if (budgetInput) budgetInput.onkeydown = (event) => { if (event.key === 'Enter') applyBudget(); };
    applyBudget();
    const button = document.querySelector('#auto-btn');
    if (button) button.addEventListener('click', (event) => {
      event.stopImmediatePropagation();
      if (running) stop();
      else { running = true; button.textContent = '자동매매 중지'; run(); }
    }, true);
  });
})();




