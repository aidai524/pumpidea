"use strict";

const $ = (id) => document.getElementById(id);
const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => (
  { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
const pct1 = (v) => (v == null ? "—" : (v * 100).toFixed(1) + "%");
const pct2 = (v) => (v == null ? "—" : (v * 100).toFixed(2) + "%");
const num = (v) => (v == null ? "—" : Number(v).toLocaleString("en-US"));
const dur = (v) => (v == null ? "—" : v < 3600 ? Math.round(v) + " s" : (v / 3600).toFixed(1) + " h");

function kpi(k, v, h) {
  return `<div class="kpi"><div class="k">${esc(k)}</div>
    <div class="v">${esc(v)}</div><div class="h">${esc(h || "")}</div></div>`;
}

function renderKpis(d) {
  const k = d.kpis || {};
  $("kpis").innerHTML = [
    kpi("Launches · 24h", num(k.launches), "all kinds"),
    kpi("True graduations", num(k.graduations), pct2(k.graduation_rate) + " of launches"),
    kpi("Instant bundles", num(k.instant_bundles), pct1(k.instant_share) + " of graduations"),
    kpi("Organic rate", pct2(k.organic_rate), "median " + dur(k.organic_median_s)),
    kpi("Pools −90% in 30m", pct1(k.pool_death_share), "median death " + dur(k.median_collapse_s)),
  ].join("");
}

function watchRows(rows, mode) {
  if (!rows || !rows.length) return `<tr><td colspan="5" style="color:var(--muted)">waiting for candidates…</td></tr>`;
  return rows.map((r) => {
    const flags = (r.flags || []).map((f) => `<span class="flag">${esc(f.replace(/_/g, " "))}</span>`).join("");
    const p = mode === "rug" ? r.p_rug : r.p_grad;
    const cls = mode === "rug" ? "hot" : "warm";
    return `<tr>
      <td class="sym">${esc(r.symbol)}${flags}</td>
      <td class="num">${esc(r.age)}</td>
      <td class="num">${esc(r.reserve_sol)} SOL</td>
      <td class="num">${num(r.unique_buyers_60s)} buyers</td>
      <td class="num ${cls}">${p.toFixed(1)}%</td>
    </tr>`;
  }).join("");
}

function renderWall(d) {
  $("wall").innerHTML = (d.stories || []).map((s) => `
    <a class="card" href="${esc(s.link)}" target="_blank" rel="noopener">
      <img src="cards/${esc(s.id)}.svg" alt="${esc(s.title)}" loading="lazy">
      <div class="meta"><span class="t">${esc(s.kicker)}</span><span>${esc(s.title)}</span></div>
    </a>`).join("");
}

function renderTape(d) {
  $("tape").innerHTML = `
    <tr><th>Token</th><th>Label</th><th class="right">To graduation</th>
        <th class="right">Peak SOL</th><th class="right">Same ticker</th>
        <th class="right">Pool vs open</th><th>Launched</th></tr>` +
    (d.tape || []).map((r) => {
      const cls = r.label === "instant_bundle" ? "instant" : r.label === "organic" ? "organic" : "none";
      const label = r.label === "instant_bundle" ? "instant" : r.label === "organic" ? "organic" : "—";
      const pv = r.price_vs_open == null ? "—" : r.price_vs_open + "%";
      return `<tr>
        <td class="sym"><a href="${esc(r.link)}" target="_blank" rel="noopener">${esc(r.symbol)}</a></td>
        <td><span class="chip ${cls}">${label}</span></td>
        <td class="right">${esc(r.seconds)}</td>
        <td class="right">${esc(r.peak_sol)}</td>
        <td class="right">${num(r.copies)}</td>
        <td class="right">${pv}</td>
        <td>${esc(r.when)}</td>
      </tr>`;
    }).join("");
}

async function refresh() {
  try {
    const res = await fetch("data.json?t=" + Date.now(), { cache: "no-store" });
    const d = await res.json();
    renderKpis(d);
    $("watch-grad").innerHTML = watchRows(d.live?.graduation, "grad");
    $("watch-rug").innerHTML = watchRows(d.live?.rug, "rug");
    renderWall(d);
    renderTape(d);
    $("updated").textContent = "data " + (d.source_generated_at || d.generated_at);
    $("gen").textContent = "page built " + d.generated_at;
    $("dot").classList.remove("stale");
  } catch (e) {
    $("dot").classList.add("stale");
    $("updated").textContent = "waiting for builder…";
  }
}

refresh();
setInterval(refresh, 15000);
