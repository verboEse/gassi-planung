"use strict";

const state = {
  year: null,        // null = aktuelle Woche (Server entscheidet)
  week: null,
  data: null,
  selectedPerson: null,
};

const SLOT_KEYS = ["morning", "noon", "evening"];
const PREF_OPTIONS = [
  { value: "", label: "–" },
  { value: "3", label: "3 gern" },
  { value: "2", label: "2 ok" },
  { value: "1", label: "1 ungern" },
  { value: "-1", label: "🚫 blockiert" },
];

// ---------- Helpers ----------------------------------------------------------

function isoWeekOf(date) {
  const d = new Date(Date.UTC(date.getFullYear(), date.getMonth(), date.getDate()));
  const dayNum = (d.getUTCDay() + 6) % 7; // Mo=0 … So=6
  d.setUTCDate(d.getUTCDate() - dayNum + 3); // Donnerstag dieser Woche
  const firstThursday = new Date(Date.UTC(d.getUTCFullYear(), 0, 4));
  const fday = (firstThursday.getUTCDay() + 6) % 7;
  firstThursday.setUTCDate(firstThursday.getUTCDate() - fday + 3);
  const week = 1 + Math.round((d - firstThursday) / (7 * 86400000));
  return { year: d.getUTCFullYear(), week };
}

function fmtDate(iso) {
  const [, m, d] = iso.split("-");
  return `${d}.${m}.`;
}

async function api(path, options) {
  const res = await fetch(path, options);
  if (!res.ok) {
    let msg = `${res.status}`;
    try { msg = (await res.json()).detail || msg; } catch { /* ignore */ }
    throw new Error(msg);
  }
  return res.status === 204 ? null : res.json();
}

function toast(msg) {
  const el = document.getElementById("toast");
  el.textContent = msg;
  el.hidden = false;
  clearTimeout(toast._t);
  toast._t = setTimeout(() => { el.hidden = true; }, 3500);
}

// ---------- Laden ------------------------------------------------------------

async function loadWeek() {
  const params = state.year && state.week ? `?year=${state.year}&week=${state.week}` : "";
  const data = await api(`/api/week${params}`);
  state.data = data;
  state.year = data.year;
  state.week = data.week;
  if (!data.persons.some(p => p.id === state.selectedPerson)) {
    state.selectedPerson = data.persons.length ? data.persons[0].id : null;
  }
  renderAll();
}

function shiftWeek(days) {
  const monday = new Date(`${state.data.dates[0]}T00:00:00`);
  monday.setDate(monday.getDate() + days);
  const { year, week } = isoWeekOf(monday);
  state.year = year;
  state.week = week;
  loadWeek().catch(e => toast(e.message));
}

// ---------- Rendering ----------------------------------------------------------

function renderAll() {
  document.getElementById("weekLabel").textContent = `KW ${state.week} / ${state.year}`;
  renderPlan();
  renderStats();
  renderTabs();
  renderCalLink();
  renderGrid();
  renderPersonList();
}

function renderPlan() {
  const { plan, persons } = state.data;
  const wrap = document.getElementById("planTable");
  if (!persons.length) {
    wrap.innerHTML = `<p class="empty">Noch keine Personen angelegt – unten hinzufügen.</p>`;
    return;
  }
  const label = { morning: "Morgens", noon: "Mittags", evening: "Abends" };
  let html = `<table><thead><tr><th>Tag</th>${SLOT_KEYS.map(s => `<th>${label[s]}</th>`).join("")}</tr></thead><tbody>`;
  for (const day of plan.days) {
    const weekend = day.weekday === "Sa" || day.weekday === "So" ? " class=\"weekend\"" : "";
    html += `<tr${weekend ? ' class="weekend"' : ""}><td class="day-label">${day.weekday}<span class="date">${fmtDate(day.date)}</span></td>`;
    for (const s of SLOT_KEYS) {
      const cell = day.slots[s];
      if (cell.unassigned) {
        html += `<td class="unassigned">⚠️ frei</td>`;
      } else {
        const dots = "●".repeat(cell.pref) + "○".repeat(3 - cell.pref);
        html += `<td><span class="assignee" style="background:${cell.color}">${cell.name}<span class="pref-dots">${dots}</span></span></td>`;
      }
    }
    html += "</tr>";
  }
  wrap.innerHTML = html + "</tbody></table>";
}

function renderStats() {
  const el = document.getElementById("planStats");
  const { counts } = state.data.plan;
  if (!counts.length) { el.innerHTML = ""; return; }
  el.innerHTML = counts.map(c =>
    `<span class="stat-chip" style="border-color:${c.color}"><b>${c.name}</b>: ${c.count}×</span>`
  ).join("");
}

function renderTabs() {
  const el = document.getElementById("personTabs");
  const { persons } = state.data;
  if (!persons.length) { el.innerHTML = ""; return; }
  el.innerHTML = "";
  for (const p of persons) {
    const btn = document.createElement("button");
    btn.className = "tab" + (p.id === state.selectedPerson ? " active" : "");
    btn.textContent = p.name;
    if (p.id === state.selectedPerson) btn.style.background = p.color;
    btn.style.borderColor = p.color;
    btn.onclick = () => { state.selectedPerson = p.id; renderTabs(); renderGrid(); renderCalLink(); };
    el.appendChild(btn);
  }
}

function renderCalLink() {
  const el = document.getElementById("calLink");
  const p = state.data.persons.find(x => x.id === state.selectedPerson);
  if (!p) { el.innerHTML = ""; return; }
  const url = `${location.origin}/api/calendar/${p.id}.ics`;
  el.innerHTML = "";
  const label = document.createElement("span");
  label.textContent = `📅 iCal-Feed für ${p.name}: `;
  const input = document.createElement("input");
  input.type = "text";
  input.readOnly = true;
  input.value = url;
  input.onclick = () => input.select();
  const copyBtn = document.createElement("button");
  copyBtn.className = "secondary";
  copyBtn.textContent = "Kopieren";
  copyBtn.onclick = async () => {
    try {
      await navigator.clipboard.writeText(url);
      copyBtn.textContent = "✓ Kopiert";
    } catch {
      input.select();
      document.execCommand("copy");
      copyBtn.textContent = "✓ Kopiert";
    }
    setTimeout(() => { copyBtn.textContent = "Kopieren"; }, 2000);
  };
  const dl = document.createElement("a");
  dl.href = url;
  dl.textContent = "Download";
  dl.className = "cal-download";
  el.append(label, input, copyBtn, dl);
}

function renderGrid() {
  const wrap = document.getElementById("editGrid");
  const { persons, plan, prefs } = state.data;
  const p = persons.find(x => x.id === state.selectedPerson);
  if (!p) {
    wrap.innerHTML = `<p class="empty">Keine Person ausgewählt.</p>`;
    return;
  }
  const label = { morning: "Morgens", noon: "Mittags", evening: "Abends" };
  const myPrefs = prefs[String(p.id)] || {};
  wrap.innerHTML = "";
  const table = document.createElement("table");
  table.innerHTML = `<thead><tr><th>Tag</th>${SLOT_KEYS.map(s => `<th>${label[s]}</th>`).join("")}</tr></thead>`;
  const tbody = document.createElement("tbody");
  plan.days.forEach((day, idx) => {
    const wd = String(idx + 1); // 1=Mo … 7=So – Prioritäten gelten allgemeingültig pro Wochentag
    const tr = document.createElement("tr");
    tr.innerHTML = `<td class="day-label">${day.weekday}<span class="date">${fmtDate(day.date)}</span></td>`;
    for (const s of SLOT_KEYS) {
      const td = document.createElement("td");
      const sel = document.createElement("select");
      const current = (myPrefs[wd] && myPrefs[wd][s] !== undefined)
        ? String(myPrefs[wd][s]) : "";
      for (const opt of PREF_OPTIONS) {
        const o = document.createElement("option");
        o.value = opt.value;
        o.textContent = opt.label;
        if (o.value === current) o.selected = true;
        sel.appendChild(o);
      }
      if (current === "-1") sel.classList.add("blocked");
      if (current === "3") sel.classList.add("high");
      sel.onchange = () => setPref(p.id, idx + 1, s, sel.value === "" ? null : parseInt(sel.value, 10));
      td.appendChild(sel);
      tr.appendChild(td);
    }
    tbody.appendChild(tr);
  });
  table.appendChild(tbody);
  wrap.appendChild(table);
}

function renderPersonList() {
  const el = document.getElementById("personList");
  const { persons } = state.data;
  el.innerHTML = "";
  if (!persons.length) {
    el.innerHTML = `<p class="empty">Noch niemand eingetragen.</p>`;
    return;
  }
  for (const p of persons) {
    const chip = document.createElement("span");
    chip.className = "person-chip";
    chip.style.background = p.color;
    chip.textContent = p.name;
    const del = document.createElement("button");
    del.textContent = "✕";
    del.title = `${p.name} entfernen`;
    del.onclick = () => removePerson(p);
    chip.appendChild(del);
    el.appendChild(chip);
  }
}

// ---------- Aktionen -----------------------------------------------------------

async function setPref(personId, weekday, slot, value) {
  try {
    await api("/api/prefs", {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ person_id: personId, weekday, slot, value }),
    });
    await loadWeek(); // Plan live neu berechnen
  } catch (e) {
    toast(e.message);
    await loadWeek().catch(() => {});
  }
}

async function removePerson(p) {
  if (!confirm(`${p.name} wirklich entfernen? Alle Prioritäten gehen verloren.`)) return;
  try {
    await api(`/api/persons/${p.id}`, { method: "DELETE" });
    await loadWeek();
  } catch (e) { toast(e.message); }
}

// ---------- Init ---------------------------------------------------------------

document.getElementById("prevWeek").onclick = () => shiftWeek(-7);
document.getElementById("nextWeek").onclick = () => shiftWeek(7);
document.getElementById("todayBtn").onclick = () => { state.year = null; state.week = null; loadWeek().catch(e => toast(e.message)); };

document.getElementById("addPersonForm").onsubmit = async (ev) => {
  ev.preventDefault();
  const name = document.getElementById("newName").value.trim();
  const color = document.getElementById("newColor").value;
  if (!name) return;
  try {
    await api("/api/persons", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ name, color }),
    });
    document.getElementById("newName").value = "";
    await loadWeek();
  } catch (e) { toast(e.message); }
};

loadWeek().catch(e => toast(e.message));
