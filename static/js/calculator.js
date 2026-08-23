// SmartAttend — attendance calculator
(function () {
  function calculate() {
    const total = parseFloat(document.getElementById('calcTotal').value) || 0;
    const attended = parseFloat(document.getElementById('calcAttended').value) || 0;
    const required = parseFloat(document.getElementById('calcRequired').value) || 75;

    const pctEl = document.getElementById('calcCurrentPct');
    const badgeEl = document.getElementById('calcBadge');
    const fillEl = document.getElementById('calcProgressFill');
    const msgEl = document.getElementById('calcMessage');
    const missEl = document.getElementById('calcCanMiss');
    const needEl = document.getElementById('calcNeedAttend');

    if (total <= 0 || attended > total || attended < 0) {
      msgEl.textContent = 'Enter a valid total and attended count (attended cannot exceed total).';
      pctEl.textContent = '--%';
      badgeEl.textContent = '—';
      badgeEl.className = 'badge';
      fillEl.style.width = '0%';
      missEl.textContent = '0';
      needEl.textContent = '0';
      return;
    }

    const currentPct = (attended / total) * 100;
    pctEl.textContent = currentPct.toFixed(1) + '%';
    fillEl.style.width = Math.min(currentPct, 100) + '%';

    let status, badgeClass, fillClass;
    if (currentPct >= required) { status = '✓ Eligible'; badgeClass = 'badge-safe'; fillClass = 'fill-safe'; }
    else if (currentPct >= required - 10) { status = '⚠ At Risk'; badgeClass = 'badge-warning'; fillClass = 'fill-warning'; }
    else { status = '✕ Not Eligible'; badgeClass = 'badge-critical'; fillClass = 'fill-critical'; }
    badgeEl.textContent = status;
    badgeEl.className = 'badge ' + badgeClass;
    fillEl.className = 'progress-fill ' + fillClass;

    let canMiss = 0;
    let needAttend = 0;

    if (currentPct >= required) {
      // attended / (total + x) >= required/100  =>  x <= attended*100/required - total
      canMiss = Math.max(0, Math.floor((attended * 100 / required) - total));
      msgEl.textContent = `You can miss ${canMiss} more class${canMiss !== 1 ? 'es' : ''} and remain at or above ${required}%.`;
    } else {
      // (attended + x) / (total + x) >= required/100
      const denom = 100 - required;
      if (denom > 0) {
        needAttend = Math.max(0, Math.ceil(((required * total) - (100 * attended)) / denom));
      }
      msgEl.textContent = `Attend the next ${needAttend} consecutive class${needAttend !== 1 ? 'es' : ''} to reach ${required}%.`;
    }

    missEl.textContent = canMiss;
    needEl.textContent = needAttend;
  }

  document.addEventListener('DOMContentLoaded', () => {
    const btn = document.getElementById('calcBtn');
    if (btn) {
      btn.addEventListener('click', calculate);
      calculate();
    }
  });
})();
