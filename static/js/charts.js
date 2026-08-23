// SmartAttend — analytics charts (Chart.js), themed to match glassmorphism UI
(function () {
  function cssVar(name) {
    return getComputedStyle(document.documentElement).getPropertyValue(name).trim();
  }

  async function loadData() {
    const res = await fetch('/api/analytics-data');
    return res.json();
  }

  function baseGridColor() {
    const isDark = document.documentElement.getAttribute('data-theme') === 'dark' ||
      (document.documentElement.getAttribute('data-theme') === 'system' &&
        window.matchMedia('(prefers-color-scheme: dark)').matches);
    return isDark ? 'rgba(255,255,255,0.08)' : 'rgba(20,30,60,0.08)';
  }

  function textColor() {
    const isDark = document.documentElement.getAttribute('data-theme') === 'dark' ||
      (document.documentElement.getAttribute('data-theme') === 'system' &&
        window.matchMedia('(prefers-color-scheme: dark)').matches);
    return isDark ? '#b0b4c4' : '#5b6172';
  }

  Chart.defaults.font.family = "'Inter', sans-serif";
  Chart.defaults.color = textColor();

  async function buildCharts() {
    const data = await loadData();
    const weeks = window.ANALYTICS_WEEKS || [];
    const grid = baseGridColor();

    // Weekly trend line chart
    const trendCtx = document.getElementById('trendChart');
    if (trendCtx) {
      new Chart(trendCtx, {
        type: 'line',
        data: {
          labels: weeks.map((w) => w.label),
          datasets: [{
            label: 'Attendance %',
            data: weeks.map((w) => w.percentage),
            borderColor: '#4d7cfe',
            backgroundColor: 'rgba(77,124,254,0.14)',
            tension: 0.4,
            fill: true,
            pointRadius: 3,
            pointBackgroundColor: '#4d7cfe',
            spanGaps: true,
          }],
        },
        options: {
          responsive: true,
          plugins: { legend: { display: false } },
          scales: {
            y: { min: 0, max: 100, grid: { color: grid }, ticks: { callback: (v) => v + '%' } },
            x: { grid: { display: false } },
          },
        },
      });
    }

    // Present vs Absent doughnut
    const paCtx = document.getElementById('presentAbsentChart');
    if (paCtx) {
      const pa = data.present_absent || { present: 0, absent: 0 };
      new Chart(paCtx, {
        type: 'doughnut',
        data: {
          labels: ['Present', 'Absent'],
          datasets: [{
            data: [pa.present, pa.absent],
            backgroundColor: ['#2fbf71', '#f0455a'],
            borderWidth: 0,
            hoverOffset: 6,
          }],
        },
        options: {
          responsive: true,
          cutout: '68%',
          plugins: { legend: { position: 'bottom' } },
        },
      });
    }

    // Subject comparison bar chart
    const subCtx = document.getElementById('subjectChart');
    if (subCtx) {
      const subjects = data.subjects || [];
      new Chart(subCtx, {
        type: 'bar',
        data: {
          labels: subjects.map((s) => s.name),
          datasets: [{
            label: 'Attendance %',
            data: subjects.map((s) => s.percentage),
            backgroundColor: subjects.map((s) =>
              s.percentage >= 75 ? '#2fbf71' : s.percentage >= 65 ? '#f5a623' : '#f0455a'),
            borderRadius: 8,
            maxBarThickness: 42,
          }],
        },
        options: {
          responsive: true,
          plugins: { legend: { display: false } },
          scales: {
            y: { min: 0, max: 100, grid: { color: grid }, ticks: { callback: (v) => v + '%' } },
            x: { grid: { display: false } },
          },
        },
      });
    }

    // Semester trend bar/line
    const semCtx = document.getElementById('semesterTrendChart');
    if (semCtx) {
      const trend = data.semester_trend || [];
      new Chart(semCtx, {
        type: 'line',
        data: {
          labels: trend.map((s) => s.label),
          datasets: [{
            label: 'Semester Attendance %',
            data: trend.map((s) => s.percentage),
            borderColor: '#a855f7',
            backgroundColor: 'rgba(168,85,247,0.14)',
            tension: 0.35,
            fill: true,
            pointRadius: 4,
            pointBackgroundColor: '#a855f7',
          }],
        },
        options: {
          responsive: true,
          plugins: { legend: { display: false } },
          scales: {
            y: { min: 0, max: 100, grid: { color: grid }, ticks: { callback: (v) => v + '%' } },
            x: { grid: { display: false } },
          },
        },
      });
    }
  }

  document.addEventListener('DOMContentLoaded', buildCharts);
})();
