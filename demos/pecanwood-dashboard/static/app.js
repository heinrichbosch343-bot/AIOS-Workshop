/* Pecanwood Portfolio dashboard.
   Real data comes from /api/portfolio (scraped public listings + market pages).
   The lead-responder feed and per-listing activity are SAMPLE and labeled so. */

let P = null;           // portfolio payload
let chart = null;

const R = (n) => "R" + Math.round(n).toLocaleString("en-ZA").replace(/,/g, " ");
const RM = (n) => "R" + (n / 1e6).toFixed(n >= 1e7 ? 0 : 2).replace(/\.00$/, "") + "M";

async function boot() {
  P = await (await fetch("/api/portfolio")).json();
  renderKpis();
  renderScatter();
  renderCompetitors();
  renderSolds();
  renderTable();
  renderReports();
  runLeadSim();
  document.getElementById("median-label").textContent = R(P.stats.median_rpm2) + "/m²";
  document.getElementById("queue-count").textContent =
    P.stats.active_sale - P.listings.filter((l) => l.report).length;
  document.getElementById("search").addEventListener("input", renderTable);
  document.getElementById("sort").addEventListener("change", renderTable);
  document.getElementById("replay").addEventListener("click", runLeadSim);
  document.getElementById("drawer-close").addEventListener("click", closeDrawer);
  document.getElementById("drawer-backdrop").addEventListener("click", closeDrawer);
}

/* ---------------- KPIs ---------------- */
function renderKpis() {
  const s = P.stats;
  const mandated = P.listings.filter((l) => l.mandate).length;
  const el = document.getElementById("kpis");
  el.innerHTML = [
    kpi("Live listings", s.active_sale, "of 880 homes"),
    kpi("Book value", RM(s.book_value), "asking total"),
    kpi("Estate median", R(s.median_rpm2) + "<small>/m²</small>", `${s.priced_listings} listings`),
    kpi("Sole mandates", mandated, `of ${s.active_sale}`),
    kpi("Deals concluded", P.agent.office_deals_public, "public record"),
  ].join("");
}
function kpi(label, value, foot) {
  return `<div class="kpi">
    <div class="label"><span>${label}</span></div>
    <div class="value">${value}</div>
    <div class="foot">${foot}</div>
  </div>`;
}

/* ---------------- scatter ---------------- */
function renderScatter() {
  const priced = P.listings.filter((l) => l.size && l.price > 1_000_000);
  const pts = priced.map((l) => ({ x: l.size, y: l.price, ref: l.ref }));
  const maxSize = Math.ceil((Math.max(...priced.map((l) => l.size)) * 1.08) / 50) * 50;
  const med = P.stats.median_rpm2;

  chart = new Chart(document.getElementById("scatter"), {
    type: "scatter",
    data: {
      datasets: [
        {
          label: "Estate median",
          type: "line",
          data: [{ x: 0, y: 0 }, { x: maxSize, y: maxSize * med }],
          borderColor: "#B07C2E",
          borderWidth: 2,
          borderDash: [7, 5],
          pointRadius: 0,
          order: 2,
        },
        {
          label: "Your listings",
          data: pts,
          backgroundColor: "rgba(46,111,184,.82)",
          borderColor: "#fff",
          borderWidth: 1.5,
          pointRadius: 7,
          pointHoverRadius: 10,
          order: 1,
        },
      ],
    },
    options: {
      maintainAspectRatio: false,
      onClick: (e, els) => {
        const hit = els.find((x) => x.datasetIndex === 1);
        if (hit) openDrawer(pts[hit.index].ref);
      },
      scales: {
        x: {
          title: { display: true, text: "Home size (m²)", color: "#6E7683", font: { size: 11 } },
          grid: { color: "rgba(28,39,51,.06)" },
          ticks: { color: "#6E7683", font: { size: 11 } },
          min: 0, max: maxSize,
        },
        y: {
          title: { display: true, text: "Asking price", color: "#6E7683", font: { size: 11 } },
          grid: { color: "rgba(28,39,51,.06)" },
          ticks: { color: "#6E7683", font: { size: 11 }, callback: (v) => "R" + v / 1e6 + "M" },
          min: 0,
        },
      },
      plugins: {
        legend: { display: false },
        tooltip: {
          backgroundColor: "#1C2733",
          padding: 10,
          displayColors: false,
          filter: (item) => item.datasetIndex === 1,
          callbacks: {
            label: (c) => {
              const l = P.listings.find((x) => x.ref === c.raw.ref);
              return [
                l.address || l.title,
                `${RM(l.price)} · ${l.size} m² · ${R(l.rpm2)}/m²`,
                (l.vs_median_pct >= 0 ? "+" : "") + l.vs_median_pct + "% vs estate median",
              ];
            },
          },
        },
      },
    },
  });
}

/* ---------------- competitors + solds ---------------- */
function renderCompetitors() {
  const max = Math.max(...P.competitors.map((c) => c.listings));
  document.getElementById("competitors").innerHTML = P.competitors
    .map(
      (c) => `<div class="comp-row">
        <span class="comp-name ${c.us ? "us" : ""}">${c.name}${c.us ? " (you)" : ""}</span>
        <div class="comp-bar"><div class="comp-fill ${c.us ? "us" : ""}" style="width:${(c.listings / max) * 100}%"></div></div>
        <span class="comp-n">${c.listings}</span>
      </div>`
    )
    .join("");
}
function renderSolds() {
  document.getElementById("solds").innerHTML = P.recent_solds
    .slice(0, 6)
    .map((d) => `<div class="sold-item"><span>${d.title.replace(" Sold in Pecanwood Estate", "")}</span><span class="p">${RM(d.price)}</span></div>`)
    .join("");
}

/* ---------------- table ---------------- */
function renderTable() {
  const q = document.getElementById("search").value.trim().toLowerCase();
  const sort = document.getElementById("sort").value;
  let rows = P.listings.slice();

  if (q) rows = rows.filter((l) =>
    [l.address, l.title, l.ref, l.mandate].filter(Boolean).join(" ").toLowerCase().includes(q));

  const cmp = {
    "price-desc": (a, b) => b.price - a.price,
    "price-asc": (a, b) => a.price - b.price,
    "vs-desc": (a, b) => (b.vs_median_pct ?? -999) - (a.vs_median_pct ?? -999),
    "vs-asc": (a, b) => (a.vs_median_pct ?? 999) - (b.vs_median_pct ?? 999),
  }[sort];
  rows.sort(cmp);

  document.getElementById("book-count").textContent = `· ${rows.length} of ${P.listings.length}`;
  document.querySelector("#listings tbody").innerHTML = rows
    .map((l) => {
      const vs =
        l.vs_median_pct == null
          ? `<span class="vs-flat">—</span>`
          : l.vs_median_pct > 3
          ? `<span class="vs-up">+${l.vs_median_pct}%</span>`
          : l.vs_median_pct < -3
          ? `<span class="vs-down">${l.vs_median_pct}%</span>`
          : `<span class="vs-flat">${l.vs_median_pct > 0 ? "+" : ""}${l.vs_median_pct}%</span>`;
      return `<tr data-ref="${l.ref}">
        <td class="addr">${l.address || shortTitle(l)}<small>${l.address ? shortTitle(l) + " · " : ""}ref ${l.ref}</small></td>
        <td class="num"><b>${RM(l.price)}</b></td>
        <td class="num nowrap">${l.size ? l.size + " m²" : "—"}</td>
        <td class="num">${l.rpm2 ? R(l.rpm2) : "—"}</td>
        <td class="num">${vs}</td>
        <td>${l.mandate ? `<span class="mandate-badge">${l.mandate.replace("Exclusive Sole Mandate", "EXCL SOLE").replace("Sole Mandate", "SOLE")}</span>` : `<span class="mandate-none">—</span>`}</td>
        <td>${l.report ? `<a class="report-link" href="/static/reports/${l.report}" target="_blank" onclick="event.stopPropagation()">Monday update</a>` : ""}</td>
      </tr>`;
    })
    .join("");

  document.querySelectorAll("#listings tbody tr").forEach((tr) =>
    tr.addEventListener("click", () => openDrawer(tr.dataset.ref)));
}
function shortTitle(l) {
  return l.title
    .replace(" For Sale in Pecanwood Estate", "")
    .replace(" For Sale in Pecanwood", "");
}

/* ---------------- reports rail ---------------- */
function renderReports() {
  const withReport = P.listings.filter((l) => l.report);
  document.getElementById("reports").innerHTML = withReport
    .map(
      (l) => `<div class="report-card">
        <div class="t">${l.address}<small>${RM(l.price)} · ${(l.vs_median_pct >= 0 ? "+" : "") + l.vs_median_pct}% vs median</small></div>
        <a class="report-link" href="/static/reports/${l.report}" target="_blank">Open PDF</a>
      </div>`
    )
    .join("");
}

/* ---------------- drawer ---------------- */
function openDrawer(ref) {
  const l = P.listings.find((x) => x.ref === ref);
  if (!l) return;
  const med = P.stats.median_rpm2;
  const maxR = Math.max(l.rpm2 || 0, med) * 1.15;
  const band = P.listings.filter(
    (x) => x.ref !== l.ref && x.price >= l.price * 0.85 && x.price <= l.price * 1.15 && x.price > 1_000_000);

  const posBars = l.rpm2
    ? `<div class="pos-bar-wrap">
         <div class="pos-bar-label"><span>This home</span><b style="color:var(--blue)">${R(l.rpm2)}/m²</b></div>
         <div class="pos-bar"><div class="pos-fill" style="width:${(l.rpm2 / maxR) * 100}%;background:var(--blue)"></div></div>
       </div>
       <div class="pos-bar-wrap">
         <div class="pos-bar-label"><span>Estate median</span><b style="color:var(--brass)">${R(med)}/m²</b></div>
         <div class="pos-bar"><div class="pos-fill" style="width:${(med / maxR) * 100}%;background:var(--brass)"></div></div>
       </div>`
    : `<p class="d-note">No size on this listing, so per-m² positioning doesn't apply (vacant land / boat garage).</p>`;

  const note = l.vs_median_pct == null
    ? ""
    : l.vs_median_pct < -3
    ? `${Math.abs(l.vs_median_pct)}% below the estate median. Well positioned.`
    : l.vs_median_pct > 3
    ? `${l.vs_median_pct}% above the estate median. Worth watching enquiries.`
    : `In line with the estate median.`;

  document.getElementById("drawer-body").innerHTML = `
    <div class="d-eyebrow">PECANWOOD ESTATE · REF ${l.ref}</div>
    <div class="d-title">${l.address || shortTitle(l)}</div>
    <div class="d-sub">${shortTitle(l)}${l.mandate ? " · " + l.mandate : ""}</div>
    <div class="d-price">${R(l.price)}</div>
    <div class="d-facts">
      ${fact("Size", l.size ? l.size + " m²" : "—")}
      ${fact("Beds / Baths", (l.beds ?? "—") + " / " + (l.baths ?? "—"))}
      ${fact("R per m²", l.rpm2 ? R(l.rpm2) : "—")}
      ${fact("vs median", l.vs_median_pct == null ? "—" : (l.vs_median_pct > 0 ? "+" : "") + l.vs_median_pct + "%")}
      ${fact("Competing", band.length + " homes ±15%")}
      ${fact("Mandate", l.mandate ? l.mandate.replace("Exclusive Sole Mandate", "Excl. Sole").replace("Sole Mandate", "Sole") : "—")}
    </div>
    <div class="d-section"><span>Market position</span><span class="chip chip-real">REAL DATA</span></div>
    ${posBars}
    ${note ? `<p class="d-note">${note}</p>` : ""}
    <div class="d-section"><span>This week's activity</span><span class="chip chip-sample">SAMPLE</span></div>
    <div class="d-facts">
      ${fact("Portal views", l.sample.views_week)}
      ${fact("Enquiries", l.sample.enquiries_week)}
      ${fact("Viewings", l.sample.viewings_booked)}
    </div>
    <div class="d-actions">
      ${l.report
        ? `<a class="solid-btn" href="/static/reports/${l.report}" target="_blank">Open Monday seller update</a>`
        : `<button class="solid-btn" onclick="toast('In the live version this generates the seller update for ${(l.address || "this home").replace(/'/g, "")} in about 20 seconds.')">Generate Monday seller update</button>`}
      <a class="ghost-btn" style="text-decoration:none" href="${l.url}" target="_blank">View live listing</a>
    </div>`;

  document.getElementById("drawer").hidden = false;
  document.getElementById("drawer-backdrop").hidden = false;
}
function fact(l, v) {
  return `<div class="d-fact"><div class="l">${l}</div><div class="v">${v}</div></div>`;
}
function closeDrawer() {
  document.getElementById("drawer").hidden = true;
  document.getElementById("drawer-backdrop").hidden = true;
}

/* ---------------- toast ---------------- */
function toast(msg) {
  let t = document.querySelector(".toast");
  if (!t) { t = document.createElement("div"); t.className = "toast"; document.body.appendChild(t); }
  t.textContent = msg;
  requestAnimationFrame(() => t.classList.add("show"));
  clearTimeout(t._h);
  t._h = setTimeout(() => t.classList.remove("show"), 4200);
}

/* ---------------- lead simulator (SAMPLE) ---------------- */
const LEAD_SCRIPT = [
  { dir: "in", meta: "PROPERTY24 · 21:47", text: "Hi, is the 4 bed at 8 Forest Crescent still available?" },
  { dir: "out", meta: "AUTO-REPLY · 8 SECONDS LATER", text: "Yes! R3 500 000, levy R6 960 pm incl. country club access. Bond or cash? Louise has Saturday 10:00 open for a viewing." },
  { dir: "in", meta: "BUYER · 21:52", text: "Bond, pre-approved. Saturday 10am works." },
  { dir: "out", meta: "AUTO-REPLY · 21:52", text: "Booked: Saturday 10:00, gate code to follow. Louise will call you in the morning." },
];

let simTimers = [];
function runLeadSim() {
  simTimers.forEach(clearTimeout);
  simTimers = [];
  const feed = document.getElementById("lead-feed");
  feed.innerHTML = "";
  let delay = 400;
  for (const m of LEAD_SCRIPT) {
    simTimers.push(setTimeout(() => {
      const div = document.createElement("div");
      div.className = `lead-msg lead-${m.dir}`;
      div.innerHTML = `<div class="meta">${m.meta}</div>${m.text}`;
      feed.appendChild(div);
      requestAnimationFrame(() => div.classList.add("show"));
      feed.scrollTop = feed.scrollHeight;
    }, delay));
    delay += m.dir === "out" ? 1900 : 1400;
  }
}

boot();
