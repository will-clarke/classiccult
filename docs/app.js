"use strict";

const els = {
  search: document.getElementById("search"),
  classicsOnly: document.getElementById("classicsOnly"),
  when: document.getElementById("when"),
  sort: document.getElementById("sort"),
  venues: document.getElementById("venues"),
  results: document.getElementById("results"),
  meta: document.getElementById("meta"),
};

let DATA = { films: [], venues: [] };
let VENUE_NAMES = {};
const todayISO = new Date().toISOString().slice(0, 10);

const fmtDay = (iso) =>
  new Date(iso + "T00:00:00").toLocaleDateString("en-GB", {
    weekday: "long", day: "numeric", month: "long",
  });

function inWindow(iso, when) {
  if (iso < todayISO) return false;            // never show past screenings
  if (when === "all") return true;
  const d = new Date(iso + "T00:00:00");
  const now = new Date(todayISO + "T00:00:00");
  const diffDays = Math.round((d - now) / 86400000);
  if (when === "today") return diffDays === 0;
  if (when === "week") return diffDays >= 0 && diffDays < 7;
  if (when === "weekend") {
    const dow = d.getDay(); // 0 Sun .. 6 Sat
    return diffDays >= 0 && diffDays < 7 && (dow === 0 || dow === 6 || dow === 5);
  }
  return true;
}

function activeVenues() {
  const checked = [...els.venues.querySelectorAll("input:checked")].map((c) => c.value);
  return new Set(checked);
}

/** Flatten to {film, screening} pairs that pass all current filters. */
function filteredPairs() {
  const q = els.search.value.trim().toLowerCase();
  const classicsOnly = els.classicsOnly.checked;
  const when = els.when.value;
  const venues = activeVenues();
  const pairs = [];
  for (const f of DATA.films) {
    if (classicsOnly && !f.classic) continue;
    if (q) {
      const hay = (f.title + " " + (f.director || "")).toLowerCase();
      if (!hay.includes(q)) continue;
    }
    for (const s of f.screenings) {
      if (!venues.has(s.venue)) continue;
      if (!inWindow(s.date, when)) continue;
      pairs.push({ f, s });
    }
  }
  return pairs;
}

function posterImg(f) {
  if (!f.poster) return `<div class="poster"></div>`;
  return `<img class="poster" loading="lazy" src="${f.poster}" alt="" onerror="this.style.visibility='hidden'">`;
}

function metaLine(f) {
  const bits = [];
  if (f.year) bits.push(`<span class="year">${f.year}</span>`);
  if (f.director) bits.push(esc(f.director));
  if (f.runtime) bits.push(esc(f.runtime));
  if (f.certificate) bits.push(esc(f.certificate));
  return bits.join(" · ");
}

const esc = (s) =>
  String(s).replace(/[&<>"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));

const multiVenue = () => DATA.venues.length > 1;

function timePill(s, withDate) {
  const fmt = s.formats && s.formats.length ? `<span class="fmt">${s.formats.map(esc).join(" ")}</span>` : "";
  const venueTag = multiVenue() ? `<span class="venue-tag">${esc(VENUE_NAMES[s.venue] || s.venue)}</span>` : "";
  const label = (withDate ? fmtDay(s.date).replace(/^\w+ /, "") + " " : "") + esc(s.display_time);
  if (s.sold_out || !s.booking_url) {
    return `<span class="time-pill${s.sold_out ? " sold" : ""}">${label} ${fmt} ${venueTag}</span>`;
  }
  return `<a class="time-pill" href="${esc(s.booking_url)}" target="_blank" rel="noopener">${label} ${fmt} ${venueTag}</a>`;
}

function card(f, screenings, withDate) {
  const times = screenings
    .slice()
    .sort((a, b) => (a.date + a.time).localeCompare(b.date + b.time))
    .map((s) => timePill(s, withDate))
    .join("");
  const link = f.film_url
    ? `<a href="${esc(f.film_url)}" target="_blank" rel="noopener">${esc(f.title)}</a>`
    : esc(f.title);
  return `<article class="card">
    ${posterImg(f)}
    <div>
      <h3 class="title">${link}</h3>
      <p class="sub">${metaLine(f)}</p>
      <div class="times">${times}</div>
    </div>
  </article>`;
}

function render() {
  const pairs = filteredPairs();
  const sort = els.sort.value;

  if (!pairs.length) {
    els.results.innerHTML = `<p class="empty">No screenings match. Try widening the date range or turning off “Classics only”.</p>`;
    return;
  }

  let html = "";

  if (sort === "date") {
    // group by date, then by film within the date
    const byDate = new Map();
    for (const p of pairs) {
      if (!byDate.has(p.s.date)) byDate.set(p.s.date, new Map());
      const films = byDate.get(p.s.date);
      if (!films.has(p.f.title)) films.set(p.f.title, { f: p.f, ss: [] });
      films.get(p.f.title).ss.push(p.s);
    }
    for (const date of [...byDate.keys()].sort()) {
      html += `<h2 class="day-heading">${fmtDay(date)}</h2>`;
      const films = [...byDate.get(date).values()];
      films.sort((a, b) =>
        Math.min(...a.ss.map((s) => +s.time.replace(":", ""))) -
        Math.min(...b.ss.map((s) => +s.time.replace(":", ""))));
      for (const { f, ss } of films) html += card(f, ss, false);
    }
  } else {
    // flat: one card per film, all upcoming screenings as date-stamped pills
    const byFilm = new Map();
    for (const p of pairs) {
      if (!byFilm.has(p.f.title)) byFilm.set(p.f.title, { f: p.f, ss: [] });
      byFilm.get(p.f.title).ss.push(p.s);
    }
    let films = [...byFilm.values()];
    if (sort === "title") {
      films.sort((a, b) => a.f.title.localeCompare(b.f.title));
    } else if (sort === "year") {
      films.sort((a, b) => (a.f.year || 9999) - (b.f.year || 9999));
    }
    for (const { f, ss } of films) html += card(f, ss, true);
  }

  els.results.innerHTML = html;
}

function buildVenueFilters() {
  VENUE_NAMES = Object.fromEntries(DATA.venues.map((v) => [v.id, v.name]));
  els.venues.innerHTML =
    `<legend>Venues</legend>` +
    DATA.venues
      .map(
        (v) => `<label><input type="checkbox" value="${v.id}" checked> ${esc(v.name)} <span class="venue-tag">(${v.films})</span></label>`
      )
      .join("");
  // hide the venue picker entirely when there's only one
  if (DATA.venues.length <= 1) els.venues.style.display = "none";
}

function setMeta() {
  const totalScr = DATA.films.reduce((n, f) => n + f.screenings.length, 0);
  const when = DATA.generated_at ? new Date(DATA.generated_at).toLocaleString("en-GB") : "";
  els.meta.textContent = `${DATA.films.length} films · ${totalScr} screenings · ${DATA.venues.length} venue(s) · updated ${when}`;
}

async function init() {
  try {
    const res = await fetch("data/screenings.json", { cache: "no-cache" });
    DATA = await res.json();
  } catch (e) {
    els.results.innerHTML = `<p class="empty">Couldn’t load listings. ${esc(e.message)}</p>`;
    return;
  }
  buildVenueFilters();
  setMeta();
  render();
  [els.search, els.classicsOnly, els.when, els.sort].forEach((el) =>
    el.addEventListener("input", render));
  els.venues.addEventListener("change", render);
}

init();
