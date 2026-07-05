/*
 * cards.js — renders Johan's visual statistic cards beside the orb.
 *
 * Classic script exposing window.Cards:
 *   Cards.show(spec)  — render a bar/line/table/stat/list card with staggered reveal
 *   Cards.clear()     — hide the panel
 *
 * Any card may carry "facts": [{label, value}] — shown as chips above the body.
 * Specs are validated server-side too; everything here fails soft — a bad
 * card logs a warning and is skipped, the spoken answer is never affected.
 */
const Cards = (() => {
  const panel = document.getElementById('card-panel');
  const titleEl = document.getElementById('card-title');
  const bodyEl = document.getElementById('card-body');

  let chart = null; // live Chart.js instance, destroyed before each re-render

  const PALETTE = {
    accent: 'rgba(80, 190, 255, 0.85)',
    accentFill: 'rgba(80, 190, 255, 0.18)',
    grid: 'rgba(80, 120, 160, 0.14)',
    text: '#8fa8c0',
  };

  function reset() {
    if (chart) { chart.destroy(); chart = null; }
    bodyEl.replaceChildren();
  }

  function replayAnimation() {
    panel.classList.remove('hidden', 'slide-in');
    void panel.offsetWidth; // restart the CSS animation
    panel.classList.add('slide-in');
  }

  // Staggered entrance for a set of sibling elements (facts chips, list items, table rows).
  function stagger(elements, baseDelayMs, stepMs) {
    elements.forEach((el, i) => {
      el.classList.add('reveal');
      el.style.animationDelay = `${baseDelayMs + i * stepMs}ms`;
    });
  }

  function renderFacts(spec) {
    if (!Array.isArray(spec.facts) || !spec.facts.length) return;
    const wrap = document.createElement('div');
    wrap.className = 'facts';
    const chips = spec.facts.map((f) => {
      const chip = document.createElement('span');
      chip.className = 'fact';
      const label = document.createElement('em');
      label.textContent = String(f.label);
      chip.appendChild(label);
      chip.appendChild(document.createTextNode(' ' + String(f.value)));
      wrap.appendChild(chip);
      return chip;
    });
    stagger(chips, 100, 110);
    bodyEl.appendChild(wrap);
  }

  function renderChart(spec) {
    const holder = document.createElement('div');
    holder.className = 'chart-holder';
    const canvas = document.createElement('canvas');
    holder.appendChild(canvas);
    bodyEl.appendChild(holder);
    const isBar = spec.type === 'bar';
    chart = new Chart(canvas, {
      type: spec.type,
      data: {
        labels: spec.labels,
        datasets: [{
          data: spec.values,
          backgroundColor: isBar ? PALETTE.accent : PALETTE.accentFill,
          borderColor: PALETTE.accent,
          borderWidth: isBar ? 0 : 2.5,
          borderRadius: isBar ? 5 : 0,
          fill: !isBar,
          tension: 0.35,
          pointBackgroundColor: PALETTE.accent,
          pointRadius: isBar ? 0 : 3.5,
        }],
      },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        animation: { duration: 900, easing: 'easeOutQuart', delay: (ctx) => ctx.dataIndex * 70 },
        plugins: {
          legend: { display: false },
          tooltip: {
            callbacks: {
              label: (ctx) => spec.unit ? `${ctx.parsed.y} ${spec.unit}` : `${ctx.parsed.y}`,
            },
          },
        },
        scales: {
          x: { grid: { display: false }, ticks: { color: PALETTE.text, font: { size: 11 } } },
          y: {
            grid: { color: PALETTE.grid },
            ticks: {
              color: PALETTE.text,
              font: { size: 11 },
              callback: (v) => spec.unit ? `${v} ${spec.unit}` : v,
            },
          },
        },
      },
    });
  }

  function renderTable(spec) {
    const table = document.createElement('table');
    const thead = table.createTHead().insertRow();
    spec.columns.forEach((c) => {
      const th = document.createElement('th');
      th.textContent = String(c);
      thead.appendChild(th);
    });
    const tbody = table.createTBody();
    const rows = spec.rows.map((row, i) => {
      const tr = tbody.insertRow();
      if (i === spec.highlight_row) tr.classList.add('highlight');
      row.forEach((cell) => { tr.insertCell().textContent = String(cell); });
      return tr;
    });
    stagger(rows, 180, 90);
    bodyEl.appendChild(table);
  }

  function renderStat(spec) {
    const wrap = document.createElement('div');
    wrap.className = 'stat';
    const value = document.createElement('div');
    value.className = 'stat-value';
    value.textContent = String(spec.value);
    wrap.appendChild(value);
    if (spec.label) {
      const label = document.createElement('div');
      label.className = 'stat-label';
      label.textContent = String(spec.label);
      wrap.appendChild(label);
    }
    if (spec.delta) {
      const delta = document.createElement('div');
      const negative = /^[-−▼]/.test(String(spec.delta).trim());
      delta.className = 'stat-delta ' + (negative ? 'down' : 'up');
      delta.textContent = String(spec.delta);
      wrap.appendChild(delta);
    }
    stagger(Array.from(wrap.children), 120, 160);
    bodyEl.appendChild(wrap);
  }

  function renderList(spec) {
    const ul = document.createElement('ul');
    ul.className = 'detail-list';
    const items = spec.items.map((item) => {
      const li = document.createElement('li');
      if (item.label) {
        const label = document.createElement('span');
        label.className = 'li-label';
        label.textContent = String(item.label);
        li.appendChild(label);
      }
      const text = document.createElement('span');
      text.className = 'li-text';
      text.textContent = String(item.text);
      li.appendChild(text);
      ul.appendChild(li);
      return li;
    });
    stagger(items, 220, 150);
    bodyEl.appendChild(ul);
  }

  function isValid(spec) {
    if (!spec || typeof spec !== 'object') return false;
    if (spec.type === 'bar' || spec.type === 'line') {
      return Array.isArray(spec.labels) && Array.isArray(spec.values)
        && spec.labels.length > 0 && spec.labels.length === spec.values.length
        && spec.values.every((v) => typeof v === 'number' && isFinite(v));
    }
    if (spec.type === 'table') {
      return Array.isArray(spec.columns) && Array.isArray(spec.rows)
        && spec.columns.length > 0 && spec.rows.length > 0
        && spec.rows.every((r) => Array.isArray(r) && r.length === spec.columns.length);
    }
    if (spec.type === 'stat') {
      return spec.value !== undefined && spec.value !== null;
    }
    if (spec.type === 'list') {
      return Array.isArray(spec.items) && spec.items.length > 0
        && spec.items.every((i) => i && typeof i.text === 'string');
    }
    return false;
  }

  function show(spec) {
    if (!isValid(spec)) {
      if (spec) console.warn('Cards: skipped malformed card spec', spec);
      return;
    }
    reset();
    titleEl.textContent = spec.title || '';
    renderFacts(spec);
    if (spec.type === 'bar' || spec.type === 'line') renderChart(spec);
    else if (spec.type === 'table') renderTable(spec);
    else if (spec.type === 'list') renderList(spec);
    else renderStat(spec);
    replayAnimation();
  }

  function clear() {
    reset();
    panel.classList.add('hidden');
  }

  return { show, clear };
})();
