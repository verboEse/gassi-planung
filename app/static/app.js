"use strict";

const state = {
  year: null,        // null = aktuelle Woche (Server entscheidet)
  week: null,
  data: null,
  me: null,
  selectedPerson: null,
  takeovers: [],
  adminData: null,
  adminUserId: null,
  gamification: null,
  profile: null,
  badgeCatalog: null,
  badgeHistory: false,
  badgeDetail: null,
  walkTarget: null,
  dogs: null,
  dogShare: null,
};

let authMode = "login";
let weekRequest = null;
let groupWalkTarget = null;
let takeoverApprovalTarget = null;
let dogSelectionResolver = null;
let calendarWalkStartInFlight = false;

const SLOT_KEYS = ["morning", "noon", "evening"];
const SLOT_LABELS = { morning: "Morgens", noon: "Mittags", evening: "Abends" };
const DOG_PROFILE_FIELDS = [
  { key: "feeding_instructions", inputId: "dogFeeding", label: "Fütterung" },
  { key: "medication_notes", inputId: "dogMedication", label: "Medikamente" },
  { key: "allergies", inputId: "dogAllergies", label: "Allergien" },
  { key: "veterinary_contact", inputId: "dogVeterinary", label: "Tierarztkontakt" },
  { key: "walk_notes", inputId: "dogWalkNotes", label: "Gassi-Hinweise" },
];
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

function parseWalkTarget(route) {
  const match = /^walk\/(date|weekday)\/([^/]+)\/(morning|noon|evening)\/(\d+)$/.exec(route);
  if (!match) return null;
  const personId = Number(match[4]);
  if (!Number.isSafeInteger(personId) || personId < 1) return null;
  if (match[1] === "date") {
    const date = new Date(`${match[2]}T00:00:00Z`);
    if (!/^\d{4}-\d{2}-\d{2}$/.test(match[2]) ||
        Number.isNaN(date.getTime()) || date.toISOString().slice(0, 10) !== match[2]) {
      return null;
    }
  } else if (!/^[1-7]$/.test(match[2])) {
    return null;
  }
  return { mode: match[1], value: match[2], slot: match[3], personId };
}

async function startWalkFromCalendarLink(target) {
  const params = new URLSearchParams({
    person_id: String(target.personId),
    slot: target.slot,
    [target.mode]: target.value,
  });
  try {
    const result = await api(`/api/walks/start?${params}`, { method: "POST" });
    if (state.walkTarget === target) {
      state.walkTarget = null;
      history.replaceState(history.state, "", `${location.pathname}${location.search}`);
    }
    toast(result.created
      ? `Gassi-Runde gestartet (${SLOT_LABELS[result.active.slot]})`
      : `Diese Gassi-Runde läuft bereits (${SLOT_LABELS[result.active.slot]})`);
    await loadGamification();
  } catch (error) {
    toast(error.message);
  }
}

async function api(path, options) {
  const res = await fetch(path, options);
  if (!res.ok) {
    let msg = `${res.status}`;
    try { msg = (await res.json()).detail || msg; } catch { /* ignore */ }
    const error = new Error(msg);
    error.status = res.status;
    throw error;
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

function decodeBase64Url(value) {
  const padded = value + "=".repeat((4 - value.length % 4) % 4);
  const binary = atob(padded.replace(/-/g, "+").replace(/_/g, "/"));
  return Uint8Array.from(binary, character => character.charCodeAt(0));
}

async function enableBrowserPush() {
  if (!("serviceWorker" in navigator) || !("PushManager" in window) || !("Notification" in window)) {
    return "unsupported";
  }
  try {
    const permission = Notification.permission === "default"
      ? await Notification.requestPermission()
      : Notification.permission;
    if (permission !== "granted") return "denied";
    const registration = await navigator.serviceWorker.register("/service-worker.js", { scope: "/" });
    let subscription = await registration.pushManager.getSubscription();
    if (!subscription) {
      const { public_key: publicKey } = await api("/api/push/public-key");
      subscription = await registration.pushManager.subscribe({
        userVisibleOnly: true,
        applicationServerKey: decodeBase64Url(publicKey),
      });
    }
    await api("/api/push/subscriptions", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(subscription.toJSON()),
    });
    return "enabled";
  } catch {
    return "unavailable";
  }
}

async function refreshPushSubscriptionButton() {
  const button = document.getElementById("removePushSubscriptionButton");
  if (!("serviceWorker" in navigator) || !("PushManager" in window)) {
    button.hidden = true;
    return;
  }
  try {
    const registration = await navigator.serviceWorker.getRegistration("/");
    button.hidden = !registration || !(await registration.pushManager.getSubscription());
  } catch {
    button.hidden = true;
  }
}

async function removeBrowserPushSubscription() {
  const registration = await navigator.serviceWorker.getRegistration("/");
  const subscription = await registration?.pushManager.getSubscription();
  if (!subscription) return false;
  try {
    await api("/api/push/subscriptions", {
      method: "DELETE",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ endpoint: subscription.endpoint }),
    });
  } catch (error) {
    if (error.status !== 404) throw error;
  }
  await subscription.unsubscribe();
  return true;
}

// ---------- Laden ------------------------------------------------------------

async function loadTakeovers() {
  const personId = state.me?.person.id ?? state.selectedPerson;
  if (!personId) {
    state.takeovers = [];
    return;
  }
  const params = state.me ? "" : `?person_id=${personId}`;
  state.takeovers = (await api(`/api/walk-takeovers${params}`)).requests;
}

async function loadWeek(force = false) {
  const params = state.year && state.week ? `?year=${state.year}&week=${state.week}` : "";
  if (weekRequest) {
    if (!force) return weekRequest;
    await weekRequest.catch(() => {});
  }
  weekRequest = api(`/api/week${params}`).then(async data => {
    state.data = data;
    state.year = data.year;
    state.week = data.week;
    if (state.me) {
      state.selectedPerson = state.me.person.id;
    } else if (!data.persons.some(p => p.id === state.selectedPerson)) {
      state.selectedPerson = data.persons.length ? data.persons[0].id : null;
    }
    await loadTakeovers();
    renderAll();
  }).finally(() => { weekRequest = null; });
  return weekRequest;
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
  renderGamification();
  renderTabs();
  renderCalLink();
  renderGrid();
  renderPersonList();
}

function renderPlan() {
  const { plan, persons } = state.data;
  const wrap = document.getElementById("planTable");
  if (!persons.length) {
    wrap.innerHTML = `<p class="empty">Noch keine Teilnehmer registriert.</p>`;
    return;
  }
  const label = { morning: "Morgens", noon: "Mittags", evening: "Abends" };
  const viewerId = state.me?.person.id ?? state.selectedPerson;
  let html = `<table><thead><tr><th>Tag</th>${SLOT_KEYS.map(s => `<th>${label[s]}</th>`).join("")}</tr></thead><tbody>`;
  for (const day of plan.days) {
    const weekend = day.weekday === "Sa" || day.weekday === "So" ? " class=\"weekend\"" : "";
    html += `<tr${weekend ? ' class="weekend"' : ""}><td class="day-label">${day.weekday}<span class="date">${fmtDate(day.date)}</span></td>`;
    for (const s of SLOT_KEYS) {
      const cell = day.slots[s];
      if (cell.unassigned) {
        html += `<td class="unassigned">⚠️ frei</td>`;
        continue;
      }
      const slotRequests = state.takeovers.filter(request =>
        request.walk_date === day.date && request.slot === s
      );
      const outgoing = slotRequests.find(request => request.requester_id === viewerId);
      const incoming = slotRequests.find(request => request.assignee_id === viewerId);
      const pendingIncoming = incoming?.status === "pending";
      const pending = slotRequests.some(request =>
        request.status === "pending" || request.status === "approved"
      );
      const approvedForViewer = outgoing?.status === "approved";
      const approvedForOther = incoming?.status === "approved";
      const slotCompletions = state.gamification?.completions.filter(completion =>
        completion.date === day.date && completion.slot === s
      ) || [];
      const completed = slotCompletions.length > 0;
      const sharedWalk = slotCompletions.find(completion => completion.shared_walk_id);
      const isMine = viewerId === cell.person_id;
      const window = state.gamification?.walk_status?.window;
      const active = state.gamification?.walk_status?.active;
      const isCurrentSlot = window?.date === day.date && window?.slot === s;
      const canComplete = (isMine && !approvedForOther && !pendingIncoming) || approvedForViewer;
      const canToggle = canComplete && (completed || (!active && isCurrentSlot));
      const shownName = approvedForViewer
        ? persons.find(person => person.id === viewerId)?.name || cell.name
        : cell.name;
      const marker = completed
        ? sharedWalk
          ? `<span class="completion-mark" title="Gemeinsam mit ${sharedWalk.shared_group_size} Teilnehmenden" aria-label="Gemeinsam mit ${sharedWalk.shared_group_size} Teilnehmenden">✓ gemeinsam (${sharedWalk.shared_group_size})</span>`
          : '<span class="completion-mark" title="Erledigt" aria-label="Erledigt">✓</span>'
        : "";
      const assignee = canToggle
        ? `<button type="button" class="assignee walk-toggle${completed ? " done" : ""}" style="background:${cell.color}" data-walk-date="${day.date}" data-walk-slot="${s}" title="${completed ? "Erledigt" : "Als erledigt markieren"}" aria-label="${shownName}: ${completed ? "erledigt" : "als erledigt markieren"}">${shownName}${marker}</button>`
        : `<span class="assignee" style="background:${cell.color}">${cell.name}${marker}</span>`;
      let controls = "";
      if (pendingIncoming) {
        controls = `<div class="walk-controls"><button type="button" class="secondary emoji-button takeover-decision" data-request-id="${incoming.id}" data-approved="true" title="Übernahme freigeben" aria-label="Übernahme freigeben">✅</button><button type="button" class="secondary emoji-button takeover-decision" data-request-id="${incoming.id}" data-approved="false" title="Ich gehe selbst" aria-label="Ich gehe selbst">🐕</button><button type="button" class="secondary emoji-button group-walk-decision" data-request-id="${incoming.id}" data-requester-id="${incoming.requester_id}" data-walk-date="${day.date}" data-walk-slot="${s}" title="Gemeinsame Runde bestätigen" aria-label="Gemeinsame Runde bestätigen">👥</button></div>`;
      } else if (incoming?.status === "shared" || outgoing?.status === "shared") {
        controls = '<small class="walk-request-status">Gemeinsame Runde bestätigt</small>';
      } else if (outgoing?.status === "pending") {
        controls = '<small class="walk-request-status">Anfrage läuft</small>';
      } else if (outgoing?.status === "approved") {
        controls = '<small class="walk-request-status">Übernahme freigegeben</small>';
      } else if (outgoing?.status === "declined") {
        controls = '<small class="walk-request-status">Anfrage abgelehnt</small>';
      }
      html += `<td><div class="plan-cell">${assignee}${controls}</div></td>`;
    }
    html += "</tr>";
  }
  wrap.innerHTML = html + "</tbody></table>";
  wrap.querySelectorAll(".walk-toggle").forEach(button => {
    button.onclick = () => toggleCompletion(
      button.dataset.walkDate,
      button.dataset.walkSlot,
      button.classList.contains("done"),
    ).catch(e => toast(e.message));
  });
  wrap.querySelectorAll(".takeover-decision").forEach(button => {
    const requestId = Number(button.dataset.requestId);
    const approved = button.dataset.approved === "true";
    button.onclick = () => approved
      ? openTakeoverApprovalDialog(requestId)
      : decideTakeover(requestId, false).catch(e => toast(e.message));
  });
  wrap.querySelectorAll(".group-walk-decision").forEach(button => {
    button.onclick = () => openGroupWalkDialog(
      Number(button.dataset.requestId),
      Number(button.dataset.requesterId),
      button.dataset.walkDate,
      button.dataset.walkSlot,
    );
  });
}

function renderStats() {
  const el = document.getElementById("planStats");
  const { counts } = state.data.plan;
  if (!counts.length) { el.innerHTML = ""; return; }
  el.innerHTML = counts.map(c =>
    `<span class="stat-chip" style="border-color:${c.color}"><b>${c.name}</b>: ${c.count}×</span>`
  ).join("");
}

function renderGamification() {
  const summary = document.getElementById("gamificationSummary");
  const people = document.getElementById("gamificationPeople");
  const completions = document.getElementById("myCompletions");
  const sessionButton = document.getElementById("walkSessionButton");
  const sessionHint = document.getElementById("walkSessionHint");
  if (!state.gamification) {
    summary.textContent = "";
    people.replaceChildren();
    completions.replaceChildren();
    sessionButton.hidden = true;
    sessionHint.textContent = "";
    return;
  }
  const me = state.gamification.persons.find(person => person.id === state.me?.person.id);
  summary.textContent = me
    ? `Du: ${me.points} Punkte · Level ${me.level}`
    : "Fortschritt der Gruppe";
  const walkStatus = state.gamification.walk_status;
  const walkWindow = walkStatus.window;
  const ownTakeover = walkWindow && state.takeovers.find(request =>
    request.walk_date === walkWindow.date &&
    request.slot === walkWindow.slot &&
    request.requester_id === state.me?.person.id
  );
  const awaitingTakeover = ownTakeover?.status === "pending";
  sessionButton.hidden = !state.me;
  sessionButton.disabled = Boolean(state.me) && !walkStatus.active &&
    (!walkStatus.can_start || !walkStatus.assignee_id || awaitingTakeover);
  sessionButton.textContent = walkStatus.active
    ? "Gassi-Runde beenden"
    : awaitingTakeover ? "Anfrage läuft" : "Jetzt Gassi gehen";
  sessionHint.textContent = walkStatus.active
    ? `Gestartet: ${SLOT_LABELS[walkStatus.active.slot]}`
    : walkWindow
      ? `Aktuelles Zeitfenster: ${SLOT_LABELS[walkWindow.slot]}`
      : "Start nur im jeweiligen Zeitfenster mit 30 Minuten Toleranz möglich.";
  people.replaceChildren();
  for (const person of state.gamification.persons) {
    const row = document.createElement("div");
    row.className = "gamification-person";
    const name = document.createElement("strong");
    name.textContent = person.name;
    row.append(name, document.createTextNode(`${person.points} Punkte · Level ${person.level}`));
    for (const badge of person.badges) {
      const badgeEl = document.createElement("span");
      badgeEl.className = "badge-chip";
      badgeEl.textContent = badge.label;
      row.appendChild(badgeEl);
    }
    people.appendChild(row);
  }
  completions.replaceChildren();
  if (!state.me) return;
  const ownCompletions = state.gamification.completions.filter(
    completion => completion.person_id === state.me.person.id
  );
  if (!ownCompletions.length) {
    completions.textContent = "Noch keine erledigten Runden.";
    return;
  }
  const heading = document.createElement("strong");
  heading.textContent = "Eigene Einträge";
  completions.appendChild(heading);
  for (const completion of ownCompletions) {
    const row = document.createElement("div");
    row.className = "completion-row";
    row.appendChild(document.createTextNode(
      `${fmtDate(completion.date)} · ${SLOT_LABELS[completion.slot]}`
    ));
    const dogs = document.createElement("span");
    dogs.className = "completion-dogs";
    dogs.textContent = completion.dog_names?.length
      ? ` · ${completion.dog_names.join(", ")}`
      : " · Hunde nicht erfasst";
    row.appendChild(dogs);
    const remove = document.createElement("button");
    remove.type = "button";
    remove.className = "secondary";
    remove.textContent = "Rückgängig";
    remove.onclick = () => removeCompletion(completion.date, completion.slot)
      .catch(e => toast(e.message));
    row.appendChild(remove);
    completions.appendChild(row);
  }
}

async function loadGamification() {
  state.gamification = await api("/api/gamification");
  renderGamification();
  renderPlan();
  if (state.badgeCatalog) await loadBadgeCatalog(state.badgeHistory);
}

function renderDogCare() {
  const list = document.getElementById("dogList");
  list.replaceChildren();
  if (!state.dogs.length) {
    list.textContent = "Noch keine Hunde angelegt.";
    list.className = "dog-list empty";
    return;
  }
  list.className = "dog-list";
  for (const dog of state.dogs) {
    const card = document.createElement("section");
    card.className = "card dog-card";
    const heading = document.createElement("h3");
    heading.textContent = dog.name;
    card.appendChild(heading);

    const details = document.createElement("dl");
    details.className = "dog-details";
    for (const field of DOG_PROFILE_FIELDS) {
      const label = document.createElement("dt");
      label.textContent = field.label;
      const value = document.createElement("dd");
      value.textContent = dog[field.key] || "–";
      details.append(label, value);
    }
    card.appendChild(details);

    const compatibility = document.createElement("fieldset");
    compatibility.className = "dog-compatibilities";
    const legend = document.createElement("legend");
    legend.textContent = "Kann zusammen laufen mit";
    const options = document.createElement("div");
    options.className = "dog-compatibility-options";
    for (const other of state.dogs) {
      if (other.id === dog.id) continue;
      const label = document.createElement("label");
      const input = document.createElement("input");
      input.type = "checkbox";
      input.checked = dog.compatible_dog_ids.includes(other.id);
      input.onchange = () => updateDogCompatibility(dog, other.id, input.checked);
      label.append(input, document.createTextNode(other.name));
      options.appendChild(label);
    }
    if (state.dogs.length === 1) options.textContent = "Keine weiteren Hunde.";
    compatibility.append(legend, options);
    card.appendChild(compatibility);

    const actions = document.createElement("div");
    actions.className = "dog-card-actions";
    const edit = document.createElement("button");
    edit.type = "button";
    edit.className = "secondary";
    edit.textContent = "Bearbeiten";
    edit.onclick = () => editDog(dog);
    const remove = document.createElement("button");
    remove.type = "button";
    remove.className = "secondary";
    remove.textContent = "Löschen";
    remove.onclick = () => deleteDog(dog);
    actions.append(edit, remove);
    card.appendChild(actions);
    list.appendChild(card);
  }
}

function renderDogShare() {
  const enabled = Boolean(state.dogShare?.enabled);
  const status = document.getElementById("dogShareStatus");
  const url = document.getElementById("dogShareUrl");
  status.textContent = enabled
    ? "Die Pflegeinformationen sind über den Link öffentlich lesbar."
    : "Die Pflegeinformationen sind derzeit nicht freigegeben.";
  document.getElementById("dogShareToggleButton").textContent = enabled
    ? "Freigabe widerrufen"
    : "Freigabe aktivieren";
  url.value = state.dogShare?.share_url || "";
  url.hidden = !enabled;
  document.getElementById("copyDogShareUrl").hidden = !enabled;
}

async function loadDogCare() {
  const [dogs, share] = await Promise.all([
    api("/api/dogs"),
    api("/api/dog-care-share"),
  ]);
  state.dogs = dogs.dogs;
  state.dogShare = share;
  renderDogCare();
  renderDogShare();
}

async function updateDogCompatibility(dog, otherDogId, compatible) {
  const compatibleDogIds = new Set(dog.compatible_dog_ids);
  if (compatible) compatibleDogIds.add(otherDogId);
  else compatibleDogIds.delete(otherDogId);
  try {
    await api(`/api/dogs/${dog.id}/compatibility`, {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ compatible_dog_ids: [...compatibleDogIds] }),
    });
    await loadDogCare();
  } catch (error) {
    toast(error.message);
    await loadDogCare().catch(loadError => toast(loadError.message));
  }
}

function editDog(dog) {
  document.getElementById("dogId").value = String(dog.id);
  document.getElementById("dogName").value = dog.name;
  for (const field of DOG_PROFILE_FIELDS) {
    document.getElementById(field.inputId).value = dog[field.key];
  }
  document.getElementById("dogForm").querySelector("button[type=submit]").textContent = "Änderungen speichern";
  document.getElementById("cancelDogEdit").hidden = false;
  document.getElementById("dogName").focus();
}

function resetDogForm() {
  document.getElementById("dogForm").reset();
  document.getElementById("dogId").value = "";
  document.getElementById("dogForm").querySelector("button[type=submit]").textContent = "Hund speichern";
  document.getElementById("cancelDogEdit").hidden = true;
}

async function deleteDog(dog) {
  if (!confirm(`Hund ${dog.name} löschen? Vorhandene Hund-Zuordnungen aus der Historie werden entfernt.`)) return;
  try {
    await api(`/api/dogs/${dog.id}`, { method: "DELETE" });
    await loadDogCare();
    await loadGamification();
  } catch (error) { toast(error.message); }
}

async function requestDogSelections(personIds) {
  if (state.me && state.dogs === null) await loadDogCare();
  if (!state.dogs?.length) return {};
  if (dogSelectionResolver) return null;

  const participantIds = [...new Set(personIds)];
  const fields = document.getElementById("dogSelectionFields");
  fields.replaceChildren();
  document.getElementById("dogSelectionMessage").textContent =
    "Wähle mindestens einen Hund pro teilnehmender Person. Nicht kompatible Hunde können nicht gemeinsam laufen.";
  for (const personId of participantIds) {
    const person = state.data.persons.find(item => item.id === personId) ||
      state.adminData?.users.find(item => item.id === personId);
    const group = document.createElement("fieldset");
    group.className = "dog-selection-group";
    group.dataset.personId = String(personId);
    const legend = document.createElement("legend");
    legend.textContent = person?.name || `Person ${personId}`;
    const choices = document.createElement("div");
    choices.className = "dog-choice-list";
    for (const dog of state.dogs) {
      const label = document.createElement("label");
      const input = document.createElement("input");
      input.type = "checkbox";
      input.value = String(dog.id);
      label.append(input, document.createTextNode(dog.name));
      choices.appendChild(label);
    }
    group.append(legend, choices);
    fields.appendChild(group);
  }
  document.getElementById("dogSelectionDialog").showModal();
  return new Promise(resolve => { dogSelectionResolver = resolve; });
}

function confirmDogSelections() {
  if (!dogSelectionResolver) return;
  const selections = {};
  const selectedDogIds = new Set();
  for (const group of document.querySelectorAll("#dogSelectionFields .dog-selection-group")) {
    const personId = Number(group.dataset.personId);
    const dogIds = [...group.querySelectorAll("input:checked")].map(input => Number(input.value));
    if (!dogIds.length) {
      toast("Wähle mindestens einen Hund für jede teilnehmende Person aus.");
      return;
    }
    selections[personId] = dogIds;
    for (const dogId of dogIds) selectedDogIds.add(dogId);
  }
  const selectedDogs = [...selectedDogIds].map(id => state.dogs.find(dog => dog.id === id));
  for (let index = 0; index < selectedDogs.length; index += 1) {
    for (const other of selectedDogs.slice(index + 1)) {
      if (!selectedDogs[index].compatible_dog_ids.includes(other.id)) {
        toast("Die ausgewählten Hunde dürfen nicht gemeinsam laufen.");
        return;
      }
    }
  }
  const resolve = dogSelectionResolver;
  dogSelectionResolver = null;
  document.getElementById("dogSelectionDialog").close();
  resolve(selections);
}

async function requestTakeover(date, slot) {
  const body = { date, slot };
  if (!state.me) body.person_id = state.selectedPerson;
  await api("/api/walk-takeovers", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  toast("Übernahmeanfrage gesendet");
  await loadWeek(true);
}

async function decideTakeover(requestId, approved) {
  const body = { approved };
  if (!state.me) body.person_id = state.selectedPerson;
  await api(`/api/walk-takeovers/${requestId}`, {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  toast(approved ? "Übernahme freigegeben" : "Du nimmst die Runde selbst wahr");
  await loadWeek(true);
}

function openTakeoverApprovalDialog(requestId) {
  const request = state.takeovers.find(item => item.id === requestId);
  if (!request) return;
  const requester = state.data.persons.find(person => person.id === request.requester_id);
  takeoverApprovalTarget = requestId;
  document.getElementById("takeoverApprovalMessage").textContent =
    `${requester?.name || "Die anfragende Person"} darf die Runde ${SLOT_LABELS[request.slot]} am ${fmtDate(request.walk_date)} übernehmen. Möchtest du die Übernahme freigeben?`;
  document.getElementById("takeoverApprovalDialog").showModal();
}

async function confirmTakeoverApproval() {
  if (takeoverApprovalTarget === null) return;
  const requestId = takeoverApprovalTarget;
  document.getElementById("takeoverApprovalDialog").close();
  try {
    await decideTakeover(requestId, true);
  } catch (error) { toast(error.message); }
}

function openGroupWalkDialog(requestId, requesterId, date, slot) {
  groupWalkTarget = {
    requestId,
    personIds: [state.me?.person.id ?? state.selectedPerson, requesterId],
  };
  const requester = state.data.persons.find(person => person.id === requesterId);
  document.getElementById("groupWalkMessage").textContent =
    `Die Runde ${SLOT_LABELS[slot]} am ${fmtDate(date)} für dich und ${requester?.name || "die anfragende Person"} als gemeinsam erledigt eintragen?`;
  document.getElementById("groupWalkDialog").showModal();
}

async function confirmGroupWalk() {
  if (!groupWalkTarget) return;
  const { requestId, personIds } = groupWalkTarget;
  document.getElementById("groupWalkDialog").close();
  try {
    const dogIdsByPerson = await requestDogSelections(personIds);
    if (dogIdsByPerson === null) return;
    const body = { dog_ids_by_person: dogIdsByPerson };
    if (!state.me) body.person_id = state.selectedPerson;
    await api(`/api/walk-takeovers/${requestId}/group`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    });
    toast("Gemeinsame Runde bestätigt");
    await loadGamification();
    await loadWeek(true);
  } catch (error) { toast(error.message); }
}

async function toggleCompletion(date, slot, completed) {
  if (completed) {
    const personId = state.me ? "" : `?person_id=${state.selectedPerson}`;
    await api(`/api/completions/${date}/${slot}${personId}`, { method: "DELETE" });
  } else {
    const personId = state.me?.person.id ?? state.selectedPerson;
    const dogIdsByPerson = await requestDogSelections([personId]);
    if (dogIdsByPerson === null) return;
    const body = { date, slot, source: "plan" };
    if (!state.me) body.person_id = state.selectedPerson;
    body.dog_ids_by_person = dogIdsByPerson;
    await api("/api/completions", {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    });
  }
  await loadGamification();
  await loadWeek(true);
}

async function removeCompletion(date, slot) {
  const personId = state.me ? "" : `?person_id=${state.selectedPerson}`;
  await api(`/api/completions/${date}/${slot}${personId}`, { method: "DELETE" });
  await loadGamification();
}

function renderHeaderProfile() {
  const profile = state.profile || state.me?.person;
  if (!profile) return;
  const img = document.getElementById("headerAvatar");
  const fallback = document.getElementById("headerAvatarFallback");
  const url = profile.avatar_url;
  img.hidden = !url;
  fallback.hidden = Boolean(url);
  if (url) img.src = url;
  else fallback.textContent = profile.name.trim().slice(0, 1).toUpperCase();
  document.getElementById("avatarButton").style.background = profile.color;
  const level = profile.level ?? 1;
  const label = profile.level_name ?? `Level ${level}`;
  document.getElementById("headerLevelButton").textContent = `Level ${level} · ${label}`;
}

function renderProfile() {
  if (!state.profile) return;
  const profile = state.profile;
  document.getElementById("profileLastActivity").textContent = profile.last_activity
    ? `Letzte Aktivität: ${new Date(profile.last_activity).toLocaleString("de-DE")}`
    : "Noch keine protokollierte Aktivität.";
  document.getElementById("badgeVisibilitySetting").checked = profile.badge_visibility;
  document.getElementById("pushSetting").checked = profile.push_enabled;
  document.getElementById("reminderSetting").checked = profile.reminders_enabled;
  document.getElementById("reminderDeliveryStatus").textContent = profile.reminders_enabled
    ? "iCal-Alarme sind aktiv. Browser-Push benötigt Berechtigung auf diesem Gerät."
    : "Erinnerungen sind deaktiviert; die allgemeine Push-Einstellung bleibt separat.";
  document.getElementById("removeAvatarButton").hidden = !profile.avatar_url;
  refreshPushSubscriptionButton();
  renderHeaderProfile();
}

function badgeArtwork(badge) {
  const ns = "http://www.w3.org/2000/svg";
  const svg = document.createElementNS(ns, "svg");
  const seed = [...badge.id].reduce((value, char) => (value * 31 + char.charCodeAt(0)) >>> 0, 7);
  const palettes = [
    ["#1679a8", "#d9f0f5"], ["#d66b3d", "#ffebd9"],
    ["#598b57", "#e5f1dd"], ["#7652a3", "#eee5fa"],
    ["#bf8b24", "#fff2ce"], ["#b54e68", "#ffe5ec"],
  ];
  const [rim, face] = palettes[seed % palettes.length];
  svg.setAttribute("viewBox", "0 0 96 96");
  svg.setAttribute("role", "img");
  svg.setAttribute("aria-label", `${badge.title} Abzeichen`);
  const add = (tag, attrs) => {
    const element = document.createElementNS(ns, tag);
    for (const [key, value] of Object.entries(attrs)) element.setAttribute(key, String(value));
    svg.appendChild(element);
    return element;
  };
  const sealPoints = Array.from({ length: 24 }, (_, index) => {
    const angle = index * Math.PI / 12 - Math.PI / 2;
    const radius = index % 2 ? 39 : 44;
    return `${48 + Math.cos(angle) * radius},${48 + Math.sin(angle) * radius}`;
  }).join(" ");
  add("polygon", { points: sealPoints, fill: rim });
  add("circle", { cx: 48, cy: 48, r: 34, fill: face, stroke: "#ffffff", "stroke-width": 2 });
  add("circle", { cx: 48, cy: 48, r: 29, fill: "none", stroke: rim, "stroke-width": 1.5, opacity: 0.65 });

  const ink = "#283d4d";
  const paw = (cx, cy, scale = 1, fill = ink) => {
    add("ellipse", { cx, cy: cy + 5 * scale, rx: 9 * scale, ry: 7 * scale, fill });
    [[-8, -7], [-3, -12], [3, -12], [8, -7]].forEach(([dx, dy]) =>
      add("ellipse", { cx: cx + dx * scale, cy: cy + dy * scale, rx: 3 * scale, ry: 4 * scale, fill })
    );
  };
  const ray = (cx, cy, angle, inner, outer, color = ink, width = 3) => {
    const x1 = cx + Math.cos(angle) * inner;
    const y1 = cy + Math.sin(angle) * inner;
    const x2 = cx + Math.cos(angle) * outer;
    const y2 = cy + Math.sin(angle) * outer;
    add("path", { d: `M${x1} ${y1}L${x2} ${y2}`, fill: "none", stroke: color, "stroke-width": width, "stroke-linecap": "round" });
  };

  switch (badge.art_key) {
    case "seed":
      add("path", { d: "M47 65 C45 50 48 38 58 30", fill: "none", stroke: ink, "stroke-width": 4, "stroke-linecap": "round" });
      add("path", { d: "M49 48 C32 47 30 36 33 31 C44 30 51 35 49 48Z", fill: rim, stroke: ink, "stroke-width": 2 });
      add("path", { d: "M49 45 C61 45 68 38 67 32 C57 30 50 35 49 45Z", fill: "#80b67a", stroke: ink, "stroke-width": 2 });
      paw(48, 68, 0.55, ink);
      break;
    case "bronze-medal":
    case "gold-medal":
      add("path", { d: "M37 25L48 43L59 25L65 29L56 49L40 49L31 29Z", fill: rim, stroke: ink, "stroke-width": 2 });
      add("polygon", { points: "48,38 52,45 60,46 54,52 55,60 48,56 41,60 42,52 36,46 44,45", fill: badge.art_key === "gold-medal" ? "#e5ae37" : "#b9794c", stroke: ink, "stroke-width": 2, "stroke-linejoin": "round" });
      paw(48, 70, 0.48);
      break;
    case "seven-paws":
      [[38, 40, 0.55], [58, 39, 0.55], [48, 57, 0.65], [34, 62, 0.4], [62, 62, 0.4]].forEach(([x, y, scale]) => paw(x, y, scale));
      break;
    case "fireworks":
      [[48, 43, 0], [32, 54, 0.7], [64, 53, 1.4]].forEach(([cx, cy, offset]) => {
        for (let i = 0; i < 8; i++) ray(cx, cy, i * Math.PI / 4 + offset, 7, 14, rim, 2.4);
        add("circle", { cx, cy, r: 3.3, fill: ink });
      });
      paw(48, 72, 0.42);
      break;
    case "heart-paws":
      add("path", { d: "M48 65 C42 58 27 48 30 38 C32 29 43 30 48 39 C53 30 64 29 66 38 C69 48 54 58 48 65Z", fill: "#d96a78", stroke: ink, "stroke-width": 2.5 });
      paw(48, 48, 0.48, "#fff6e8");
      break;
    case "bloom":
      for (let i = 0; i < 6; i++) {
        const angle = i * Math.PI / 3;
        add("ellipse", { cx: 48 + Math.cos(angle) * 12, cy: 45 + Math.sin(angle) * 12, rx: 7, ry: 11, transform: `rotate(${i * 60} ${48 + Math.cos(angle) * 12} ${45 + Math.sin(angle) * 12})`, fill: i % 2 ? "#f1a4b4" : "#f6c66f", stroke: ink, "stroke-width": 1.5 });
      }
      add("circle", { cx: 48, cy: 45, r: 6, fill: "#fff1c9", stroke: ink, "stroke-width": 2 });
      paw(48, 69, 0.42);
      break;
    case "paw-globe":
      add("circle", { cx: 48, cy: 45, r: 19, fill: "#80c4c6", stroke: ink, "stroke-width": 2.5 });
      add("path", { d: "M30 45H66M48 26C39 36 39 54 48 64M48 26C57 36 57 54 48 64M34 35C42 40 54 40 62 35M34 55C42 50 54 50 62 55", fill: "none", stroke: ink, "stroke-width": 1.8 });
      paw(48, 48, 0.4, "#f6f5e9");
      break;
    case "sun-path":
      for (let i = 0; i < 12; i++) ray(48, 43, i * Math.PI / 6, 18, 25, rim, 2.5);
      add("circle", { cx: 48, cy: 43, r: 13, fill: "#f6c95e", stroke: ink, "stroke-width": 2.5 });
      paw(48, 72, 0.42);
      break;
    case "leaf-trail":
      add("path", { d: "M35 58C34 38 49 27 68 30C67 48 57 62 39 64Z", fill: "#83b979", stroke: ink, "stroke-width": 2.5 });
      add("path", { d: "M38 61C47 51 54 43 63 34M48 51L46 40M54 44L64 46", fill: "none", stroke: ink, "stroke-width": 2, "stroke-linecap": "round" });
      paw(39, 67, 0.38);
      break;
    case "paw-shield":
      add("path", { d: "M48 25L68 33V47C68 59 59 68 48 74C37 68 28 59 28 47V33Z", fill: "#82bca4", stroke: ink, "stroke-width": 2.5, "stroke-linejoin": "round" });
      paw(48, 47, 0.72, "#fff6e8");
      break;
    case "moon-trail":
      add("path", { d: "M58 28C43 31 38 51 47 62C53 69 62 69 69 64C65 78 49 81 38 73C22 61 27 37 43 28C48 25 54 25 58 28Z", fill: "#7891bd", stroke: ink, "stroke-width": 2.2 });
      [[62, 37], [34, 42], [58, 57]].forEach(([x, y]) => add("polygon", { points: `${x},${y-4} ${x+1.3},${y-1.3} ${x+4},${y} ${x+1.3},${y+1.3} ${x},${y+4} ${x-1.3},${y+1.3} ${x-4},${y} ${x-1.3},${y-1.3}`, fill: "#e9c96d" }));
      break;
    case "gift-paw":
      add("rect", { x: 29, y: 40, width: 38, height: 28, rx: 4, fill: "#d96d65", stroke: ink, "stroke-width": 2.5 });
      add("path", { d: "M48 40V68M29 49H67M48 40C35 39 34 30 40 29C46 28 48 40 48 40ZM48 40C50 28 61 28 61 34C61 39 48 40 48 40Z", fill: "#f0c762", stroke: ink, "stroke-width": 2, "stroke-linejoin": "round" });
      paw(48, 57, 0.38, "#fff6e8");
      break;
    case "snow-paw":
      for (let i = 0; i < 6; i++) {
        const angle = i * Math.PI / 3;
        ray(48, 45, angle, 3, 22, "#648db6", 3);
        [0.62, -0.62].forEach(side => ray(48 + Math.cos(angle) * 14, 45 + Math.sin(angle) * 14, angle + side, 0, 6, "#648db6", 2));
      }
      paw(48, 70, 0.4);
      break;
    default:
      add("circle", { cx: 48, cy: 48, r: 15, fill: rim });
      add("path", { d: "M48 32L52 42L63 43L55 50L57 61L48 56L39 61L41 50L33 43L44 42Z", fill: face, stroke: ink, "stroke-width": 2 });
  }

  const year = badge.event_year;
  if (year) {
    add("rect", { x: 32, y: 74, width: 32, height: 12, rx: 6, fill: rim, stroke: face, "stroke-width": 1 });
    const yearText = add("text", { x: 48, y: 82.5, "text-anchor": "middle", fill: "#ffffff", "font-size": 7, "font-family": "system-ui", "font-weight": 700 });
    yearText.textContent = String(year);
  }
  for (let i = 0; i < 2 + (seed % 3); i++) {
    const angle = (seed % 360 + i * 137) * Math.PI / 180;
    add("circle", { cx: 48 + Math.cos(angle) * 37, cy: 48 + Math.sin(angle) * 37, r: 1.5 + (i % 2), fill: face });
  }
  return svg;
}

function renderBadgeCatalog() {
  const catalog = state.badgeCatalog;
  if (!catalog) return;
  const list = document.getElementById("badgeCategories");
  list.replaceChildren();
  const { earned, available } = catalog.progress;
  document.getElementById("badgeProgressText").textContent = `${earned}/${available} Abzeichen erreicht`;
  const progress = document.getElementById("badgeProgressBar");
  progress.max = Math.max(available, 1);
  progress.value = earned;
  document.getElementById("badgeHistoryButton").textContent = state.badgeHistory
    ? "Aktuelle Abzeichen"
    : "Dein Rückblick";

  for (const category of catalog.categories) {
    const badges = catalog.badges.filter(badge => badge.category_id === category.id);
    const section = document.createElement("section");
    section.className = "badge-category";
    const heading = document.createElement("h3");
    heading.textContent = category.label;
    section.appendChild(heading);
    const items = document.createElement("div");
    items.className = "badge-items";
    for (const badge of badges) {
      const button = document.createElement("button");
      button.type = "button";
      button.className = `badge-tile${badge.earned ? " earned" : " locked"}`;
      const icon = document.createElement("span");
      icon.className = "badge-art";
      icon.setAttribute("aria-hidden", "true");
      icon.appendChild(badgeArtwork(badge));
      const title = document.createElement("span");
      title.className = "badge-title";
      title.textContent = badge.title;
      button.append(icon, title);
      if (badge.show_progress) {
        const progress = document.createElement("span");
        progress.className = "badge-tile-progress";
        const hasStreak = Number.isInteger(badge.current_streak);
        progress.textContent = hasStreak
          ? `${badge.current_streak}/${badge.best_streak}`
          : `${badge.progress}/${badge.target}`;
        button.appendChild(progress);
      } else if (badge.earned) {
        const earnedMark = document.createElement("span");
        earnedMark.className = "badge-tile-earned";
        earnedMark.textContent = "✓";
        earnedMark.setAttribute("aria-label", "Freigeschaltet");
        button.appendChild(earnedMark);
      }
      button.setAttribute("aria-label", badge.show_progress
        ? Number.isInteger(badge.current_streak)
          ? `${badge.title}, aktuelle Serie ${badge.current_streak}, Bestwert ${badge.best_streak}`
          : `${badge.title}, ${badge.earned ? "erreicht" : "Fortschritt"} ${badge.progress} von ${badge.target}`
        : `${badge.title}${badge.earned ? ", freigeschaltet" : ""}`);
      button.onclick = () => navigateApp(`badge/${badge.id}`);
      items.appendChild(button);
    }
    if (!badges.length) {
      const empty = document.createElement("p");
      empty.className = "hint";
      empty.textContent = "Noch keine Abzeichen in dieser Kategorie.";
      items.appendChild(empty);
    }
    section.appendChild(items);
    list.appendChild(section);
  }
}

function badgeConditionText(badge) {
  if (badge.condition_type === "completion-count") {
    return `Erledige ${badge.target} Gassirunden.`;
  }
  if (badge.condition_type === "full-iso-week") {
    return "Erledige mindestens eine Gassirunde an jedem der sieben Tage einer ISO-Kalenderwoche.";
  }
  if (badge.condition_type === "date-completion") {
    return `Erledige eine Gassirunde am ${fmtDate(badge.condition.date)}.`;
  }
  return badge.description;
}

async function loadBadgeDetail(id) {
  state.badgeDetail = await api(`/api/badges/${encodeURIComponent(id)}`);
  const badge = state.badgeDetail;
  const detailIcon = document.getElementById("badgeDetailIcon");
  detailIcon.replaceChildren(badgeArtwork(badge));
  detailIcon.classList.toggle("locked", !badge.earned);
  document.getElementById("badgeDetailTitle").textContent = badge.title;
  document.getElementById("badgeDetailCategory").textContent = badge.category_label;
  document.getElementById("badgeDetailDescription").textContent = badge.description;
  document.getElementById("badgeDetailCondition").textContent = badgeConditionText(badge);
  const hasStreak = Number.isInteger(badge.current_streak);
  document.getElementById("badgeDetailProgressText").textContent = badge.show_progress
    ? (hasStreak
      ? `Aktuelle Serie: ${badge.current_streak}/${badge.best_streak}`
      : (badge.earned ? "Freigeschaltet" : `Fortschritt: ${badge.progress}/${badge.target}`))
    : (badge.earned ? "Freigeschaltet" : "Noch nicht freigeschaltet");
  const progress = document.getElementById("badgeDetailProgress");
  progress.hidden = !badge.show_progress;
  progress.max = Math.max(hasStreak ? badge.best_streak : badge.target, 1);
  progress.value = hasStreak ? badge.current_streak : badge.progress;
  const participants = document.getElementById("badgeParticipants");
  participants.replaceChildren();
  if (badge.participants.length) {
    const title = document.createElement("h3");
    title.textContent = "Teilnehmer mit diesem Abzeichen";
    participants.appendChild(title);
    for (const participant of badge.participants) {
      const item = document.createElement("div");
      item.className = "badge-participant";
      const avatar = document.createElement("span");
      avatar.className = "badge-participant-avatar";
      avatar.style.background = participant.color;
      if (participant.avatar_url) {
        const image = document.createElement("img");
        image.src = participant.avatar_url;
        image.alt = "";
        avatar.appendChild(image);
      } else {
        avatar.textContent = participant.name.trim().slice(0, 1).toUpperCase();
      }
      const name = document.createElement("span");
      name.textContent = participant.name;
      item.append(avatar, name);
      participants.appendChild(item);
    }
  }
}

async function loadProfile() {
  state.profile = await api("/api/profile");
  renderProfile();
}

async function loadBadgeCatalog(history = false) {
  state.badgeHistory = history;
  state.badgeCatalog = await api(`/api/badges${history ? "?history=true" : ""}`);
  renderBadgeCatalog();
}

function navigateApp(route) {
  const hash = `#${route}`;
  if (location.hash === hash) applyAppRoute();
  else location.hash = route;
}

function applyAppRoute() {
  const route = decodeURIComponent(location.hash.slice(1));
  state.walkTarget = parseWalkTarget(route);
  const isProfile = route === "profile";
  const isBadges = route === "badges" || route === "history" || route.startsWith("badge/");
  const isDogCare = route === "dog-care";
  const isPlan = !isProfile && !isBadges && !isDogCare;
  document.getElementById("planView").hidden = !isPlan;
  document.getElementById("profileView").hidden = !isProfile;
  document.getElementById("badgesView").hidden = !isBadges;
  document.getElementById("dogCareView").hidden = !isDogCare;
  document.getElementById("dogCareButton").hidden = !state.me || isDogCare;
  document.getElementById("planHomeButton").hidden = isPlan;
  const detailId = route.startsWith("badge/") ? route.slice("badge/".length) : null;
  document.getElementById("badgeOverview").hidden = Boolean(detailId);
  document.getElementById("badgeDetail").hidden = !detailId;
  if (isProfile && state.me && !state.profile) loadProfile().catch(error => toast(error.message));
  if (isDogCare && state.me && state.dogs === null) loadDogCare().catch(error => toast(error.message));
  if (isBadges && state.me && (!state.badgeCatalog || state.badgeHistory !== (route === "history"))) {
    loadBadgeCatalog(route === "history").catch(error => toast(error.message));
  }
  if (detailId && state.me && state.badgeDetail?.id !== detailId) {
    loadBadgeDetail(detailId).catch(error => toast(error.message));
  }
  if (state.walkTarget && state.gamification && !calendarWalkStartInFlight) {
    calendarWalkStartInFlight = true;
    startWalkFromCalendarLink(state.walkTarget).finally(() => {
      calendarWalkStartInFlight = false;
    });
  }
}

function renderTabs() {
  const el = document.getElementById("personTabs");
  const persons = state.me
    ? state.data.persons.filter(p => p.id === state.me.person.id)
    : state.data.persons;
  el.hidden = Boolean(state.me);
  if (!persons.length) { el.innerHTML = ""; return; }
  el.innerHTML = "";
  for (const p of persons) {
    const btn = document.createElement("button");
    btn.className = "tab" + (p.id === state.selectedPerson ? " active" : "");
    btn.textContent = p.name;
    if (p.id === state.selectedPerson) btn.style.background = p.color;
    btn.style.borderColor = p.color;
    btn.onclick = async () => {
      state.selectedPerson = p.id;
      await loadTakeovers();
      renderTabs();
      renderPlan();
      renderGrid();
      renderCalLink();
    };
    el.appendChild(btn);
  }
}

function renderCalLink() {
  const el = document.getElementById("calLink");
  const p = state.data.persons.find(x => x.id === state.selectedPerson);
  if (!p) { el.innerHTML = ""; return; }
  const url = state.me?.calendar_url || `${location.origin}/api/calendar/${p.id}.ics`;
  el.innerHTML = "";
  const label = document.createElement("span");
  label.textContent = `iCal-Feed für ${p.name}: `;
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
      copyBtn.textContent = "Kopiert";
    } catch {
      input.select();
      document.execCommand("copy");
      copyBtn.textContent = "Kopiert";
    }
    setTimeout(() => { copyBtn.textContent = "Kopieren"; }, 2000);
  };
  const subscriptionUrl = new URL(url);
  const subscribe = document.createElement("button");
  subscribe.type = "button";
  subscribe.className = "cal-download";
  subscribe.textContent = subscriptionUrl.protocol === "https:"
    ? "HTTPS-Abo-URL kopieren"
    : "Lokales Abo einrichten";
  subscribe.onclick = async () => {
    const message = "URL kopiert. In Apple Kalender: Ablage > Neues Kalenderabo.";
    try {
      await navigator.clipboard.writeText(url);
    } catch {
      input.select();
      document.execCommand("copy");
    }
    toast(message);
  };
  el.append(label, input, copyBtn, subscribe);
  if (state.me) {
    const rotate = document.createElement("button");
    rotate.className = "secondary";
    rotate.textContent = "Link erneuern";
    rotate.title = "Der bisherige Abo-Link wird dadurch ungültig";
    rotate.onclick = async () => {
      if (!confirm("Abo-Link erneuern? Der bisherige Kalender-Link wird ungültig.")) return;
      try {
        const result = await api("/api/me/calendar-token", { method: "POST" });
        state.me.calendar_url = result.calendar_url;
        renderCalLink();
      } catch (e) { toast(e.message); }
    };
    el.appendChild(rotate);
  }
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
    const wd = String(idx + 1); // 1=Mo … 7=So; changes take effect next week
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
  document.getElementById("personsSection").hidden = Boolean(state.me);
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

function renderAdminUsers() {
  const select = document.getElementById("adminUserSelect");
  const users = state.adminData?.users || [];
  select.replaceChildren();
  for (const user of users) {
    const option = document.createElement("option");
    option.value = user.id;
    option.textContent = `${user.name}${user.is_admin ? " (Admin)" : ""}`;
    select.appendChild(option);
  }
  if (!users.some(user => user.id === state.adminUserId)) {
    state.adminUserId = users.length ? users[0].id : null;
  }
  if (state.adminUserId !== null) select.value = String(state.adminUserId);
  select.disabled = !users.length;
  renderAdminCompletionPeople(users);
  renderAdminCompletionKind();
  setAdminCompletionDateBounds();
  renderAdminPrefs();
}

function renderAdminCompletionPeople(users) {
  const takeoverSelect = document.getElementById("adminTakeoverPerson");
  const groupSelect = document.getElementById("adminGroupPeople");
  for (const select of [takeoverSelect, groupSelect]) {
    select.replaceChildren();
    for (const user of users) {
      const option = document.createElement("option");
      option.value = user.id;
      option.textContent = user.name;
      select.appendChild(option);
    }
  }
  if (state.adminUserId !== null) takeoverSelect.value = String(state.adminUserId);
}

function renderAdminCompletionKind() {
  const kind = document.getElementById("adminCompletionKind").value;
  const isGroup = kind === "group";
  const takeoverLabel = document.getElementById("adminTakeoverPersonLabel");
  const takeoverSelect = document.getElementById("adminTakeoverPerson");
  const groupLabel = document.getElementById("adminGroupPeopleLabel");
  const groupSelect = document.getElementById("adminGroupPeople");
  document.getElementById("adminSinglePersonLabel").textContent =
    kind === "normal" ? "Teilnehmer" : "Übernehmende Person";
  takeoverLabel.hidden = isGroup;
  takeoverSelect.disabled = isGroup || !takeoverSelect.options.length;
  groupLabel.hidden = !isGroup;
  groupSelect.disabled = !isGroup || !groupSelect.options.length;
}

function setAdminCompletionDateBounds() {
  const input = document.getElementById("adminCompletionDate");
  const now = new Date();
  now.setMinutes(now.getMinutes() - now.getTimezoneOffset());
  const today = now.toISOString().slice(0, 10);
  input.max = today;
  if (!input.value) input.value = today;
}

function renderAdminPrefs() {
  const wrap = document.getElementById("adminPrefsGrid");
  wrap.replaceChildren();
  const user = state.adminData?.users.find(item => item.id === state.adminUserId);
  if (!user) {
    wrap.textContent = "Keine Teilnehmer vorhanden.";
    return;
  }
  const prefs = state.adminData.prefs[String(user.id)] || {};
  const weekdays = ["Mo", "Di", "Mi", "Do", "Fr", "Sa", "So"];
  const labels = { morning: "Morgens", noon: "Mittags", evening: "Abends" };
  const table = document.createElement("table");
  const head = document.createElement("tr");
  head.appendChild(document.createElement("th")).textContent = "Tag";
  for (const slot of SLOT_KEYS) head.appendChild(document.createElement("th")).textContent = labels[slot];
  table.createTHead().appendChild(head);
  const body = table.createTBody();
  weekdays.forEach((day, index) => {
    const row = body.insertRow();
    row.insertCell().textContent = day;
    for (const slot of SLOT_KEYS) {
      const select = document.createElement("select");
      const value = prefs[String(index + 1)]?.[slot];
      for (const item of PREF_OPTIONS) {
        const option = document.createElement("option");
        option.value = item.value;
        option.textContent = item.label;
        option.selected = item.value === (value === undefined ? "" : String(value));
        select.appendChild(option);
      }
      select.onchange = () => setAdminPref(
        user.id, index + 1, slot, select.value === "" ? null : Number(select.value)
      );
      row.insertCell().appendChild(select);
    }
  });
  wrap.appendChild(table);
}

function renderAdminActivity(events) {
  const wrap = document.getElementById("adminActivity");
  wrap.replaceChildren();
  if (!events.length) {
    wrap.textContent = "Keine Aktivität in den letzten 90 Tagen.";
    return;
  }
  const table = document.createElement("table");
  const head = table.createTHead().insertRow();
  for (const title of ["Zeit", "Ereignis", "Teilnehmer", "Details"]) {
    head.insertCell().textContent = title;
  }
  const body = table.createTBody();
  const dayNames = ["Mo", "Di", "Mi", "Do", "Fr", "Sa", "So"];
  const slotNames = { morning: "Morgens", noon: "Mittags", evening: "Abends" };
  for (const event of events) {
    const row = body.insertRow();
    row.insertCell().textContent = new Date(event.occurred_at).toLocaleString("de-DE");
    row.insertCell().textContent = event.action === "login"
      ? "Anmeldung"
      : event.action === "preference_change"
        ? "Präferenz geändert"
        : "Gassirunde nachgetragen";
    row.insertCell().textContent = event.subject;
    let details;
    if (event.action === "login") {
      details = `Anmeldung von ${event.actor}`;
    } else if (event.action === "preference_change") {
      details = `${event.actor}: ${dayNames[event.details.weekday - 1]} ${slotNames[event.details.slot]} (${event.details.old_value ?? "–"} → ${event.details.new_value ?? "–"})`;
    } else {
      const kind = event.details.kind === "group"
        ? "Gruppenrunde"
        : event.details.kind === "normal" ? "Normale Runde" : "Übernommene Runde";
      const date = new Date(`${event.details.date}T00:00:00`).toLocaleDateString("de-DE");
      details = `${event.actor}: ${kind} · ${date} · ${slotNames[event.details.slot]} (${event.details.participants.join(", ")})`;
    }
    row.insertCell().textContent = details;
  }
  wrap.appendChild(table);
}

async function refreshAdminActivity() {
  if (!state.me?.person.is_admin) return;
  try {
    const activity = await api("/api/admin/activity");
    renderAdminActivity(activity.events);
  } catch (e) { toast(e.message); }
}

async function submitAdminCompletion(event) {
  event.preventDefault();
  const kind = document.getElementById("adminCompletionKind").value;
  const personIds = kind === "group"
    ? [...document.getElementById("adminGroupPeople").selectedOptions].map(option => Number(option.value))
    : [Number(document.getElementById("adminTakeoverPerson").value)];
  if (kind === "group" && personIds.length < 2) {
    toast("Wähle mindestens zwei Teilnehmende für die Gruppenrunde aus.");
    return;
  }
  try {
    const dogIdsByPerson = await requestDogSelections(personIds);
    if (dogIdsByPerson === null) return;
    const result = await api("/api/admin/completions", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        kind,
        date: document.getElementById("adminCompletionDate").value,
        slot: document.getElementById("adminCompletionSlot").value,
        person_ids: personIds,
        dog_ids_by_person: dogIdsByPerson,
      }),
    });
    toast(result.created
      ? kind === "group"
        ? "Gruppenrunde nachgetragen"
        : kind === "normal" ? "Normale Runde nachgetragen" : "Übernommene Runde nachgetragen"
      : "Für diese Runde gab es bereits einen Eintrag.");
    document.getElementById("adminGroupPeople").selectedIndex = -1;
    await loadGamification();
    await loadWeek(true);
    await refreshAdminActivity();
  } catch (error) { toast(error.message); }
}

async function loadAdminPanel() {
  if (!state.me?.person.is_admin) return;
  try {
    state.adminData = await api("/api/admin/users");
    renderAdminUsers();
    await refreshAdminActivity();
  } catch (e) { toast(e.message); }
}

async function setAdminPref(personId, weekday, slot, value) {
  try {
    const result = await api("/api/admin/prefs", {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ person_id: personId, weekday, slot, value }),
    });
    if (result.changed) {
      state.year = result.effective_year;
      state.week = result.effective_week;
    }
    await loadWeek(true);
    await loadAdminPanel();
    if (result.changed) {
      toast(`Änderung für ${state.adminData.users.find(user => user.id === personId)?.name || "Teilnehmer"} gilt ab KW ${result.effective_week}/${result.effective_year}.`);
    }
  } catch (e) {
    toast(e.message);
    await loadAdminPanel();
  }
}

// ---------- Aktionen -----------------------------------------------------------

async function setPref(personId, weekday, slot, value) {
  try {
    const result = await api("/api/prefs", {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ person_id: personId, weekday, slot, value }),
    });
    if (result.changed) {
      state.year = result.effective_year;
      state.week = result.effective_week;
    }
    await loadWeek(true);
    if (result.changed) {
      toast(`Änderung gilt ab KW ${result.effective_week}/${result.effective_year}; der Plan dieser Woche bleibt unverändert.`);
    }
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
    await loadGamification();
  } catch (e) { toast(e.message); }
}

// ---------- Init ---------------------------------------------------------------

document.getElementById("planHomeButton").onclick = () => navigateApp("plan");
document.getElementById("headerLevelButton").onclick = () => navigateApp("badges");
window.addEventListener("hashchange", applyAppRoute);
document.getElementById("avatarButton").onclick = () => {
  if (state.me) navigateApp("profile");
};
document.getElementById("changeAvatarButton").onclick = () => document.getElementById("avatarUpload").click();
document.getElementById("avatarUpload").onchange = async (event) => {
  const file = event.target.files[0];
  if (!file) return;
  try {
    state.profile = await api("/api/profile/avatar", {
      method: "PUT",
      headers: { "Content-Type": file.type },
      body: file,
    });
    renderProfile();
    toast("Profilbild gespeichert");
  } catch (error) { toast(error.message); }
  event.target.value = "";
};
document.getElementById("removeAvatarButton").onclick = async () => {
  try {
    await api("/api/profile/avatar", { method: "DELETE" });
    await loadProfile();
    toast("Profilbild entfernt");
  } catch (error) { toast(error.message); }
};
document.getElementById("profilePreferencesForm").onsubmit = async (event) => {
  event.preventDefault();
  try {
    const remindersEnabled = document.getElementById("reminderSetting").checked;
    const pushEnabled = document.getElementById("pushSetting").checked;
    const browserPushStatus = remindersEnabled || pushEnabled ? await enableBrowserPush() : null;
    state.profile = await api("/api/profile/preferences", {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        badge_visibility: document.getElementById("badgeVisibilitySetting").checked,
        push_enabled: pushEnabled,
        reminders_enabled: remindersEnabled,
      }),
    });
    renderProfile();
    if (browserPushStatus === "enabled") {
      const uses = [
        remindersEnabled && "Erinnerungen",
        pushEnabled && "Übernahmeanfragen",
      ].filter(Boolean).join(" und ");
      document.getElementById("reminderDeliveryStatus").textContent =
        `Browser-Push für ${uses} ist auf diesem Gerät aktiv.`;
      toast("Profileinstellungen gespeichert; Browser-Push aktiviert");
    } else if (browserPushStatus) {
      const reason = browserPushStatus === "denied"
        ? "Browser-Berechtigung fehlt"
        : "Browser-Push ist auf diesem Gerät nicht verfügbar";
      document.getElementById("reminderDeliveryStatus").textContent = remindersEnabled
        ? `iCal-Alarm bleibt verfügbar; ${reason}.`
        : `Übernahmeanfragen werden nicht als Browser-Push zugestellt; ${reason}.`;
      toast(`Profileinstellungen gespeichert; ${reason}`);
    } else {
      document.getElementById("reminderDeliveryStatus").textContent =
        "Erinnerungen und Push-Mitteilungen sind deaktiviert.";
      toast("Profileinstellungen gespeichert");
    }
  } catch (error) { toast(error.message); }
};
document.getElementById("removePushSubscriptionButton").onclick = async () => {
  try {
    if (!await removeBrowserPushSubscription()) {
      toast("Kein Browser-Abo vorhanden");
      return;
    }
    await refreshPushSubscriptionButton();
    document.getElementById("reminderDeliveryStatus").textContent =
      "Browser-Abo entfernt; der iCal-Alarm folgt weiterhin der Erinnerungseinstellung.";
    toast("Browser-Push-Abo entfernt");
  } catch (error) { toast(error.message); }
};
document.getElementById("badgeHistoryButton").onclick = () =>
  navigateApp(state.badgeHistory ? "badges" : "history");
document.getElementById("badgeBackButton").onclick = () =>
  navigateApp(state.badgeHistory ? "history" : "badges");

document.getElementById("prevWeek").onclick = () => shiftWeek(-7);
document.getElementById("nextWeek").onclick = () => shiftWeek(7);
document.getElementById("todayBtn").onclick = () => { state.year = null; state.week = null; loadWeek().catch(e => toast(e.message)); };

document.addEventListener("visibilitychange", () => {
  if (!document.hidden) {
    loadWeek().catch(() => {});
    loadGamification().catch(() => {});
  }
});
// ponytail: 10-second polling; use server push only if this delay becomes too noticeable.
setInterval(() => {
  if (!document.hidden) {
    loadWeek().catch(() => {});
    loadGamification().catch(() => {});
  }
}, 10_000);
setInterval(() => {
  if (!document.hidden) refreshAdminActivity();
}, 30_000);

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
    await loadGamification();
  } catch (e) { toast(e.message); }
};

document.getElementById("walkSessionButton").onclick = async () => {
  const walkStatus = state.gamification?.walk_status;
  const active = walkStatus?.active;
  try {
    if (!active) {
      const walkWindow = walkStatus?.window;
      if (!walkWindow || !walkStatus.can_start) return;
      if (!walkStatus.assignee_id) {
        toast("Für diese Runde ist keine Person eingetragen");
        return;
      }
      const ownTakeover = state.takeovers.find(request =>
        request.walk_date === walkWindow.date &&
        request.slot === walkWindow.slot &&
        request.requester_id === state.me?.person.id
      );
      if (ownTakeover?.status === "pending") return;
      if (walkStatus.assignee_id !== state.me?.person.id && ownTakeover?.status !== "approved") {
        await requestTakeover(walkWindow.date, walkWindow.slot);
        return;
      }
    }
    let body;
    if (active) {
      const dogIdsByPerson = await requestDogSelections([state.me.person.id]);
      if (dogIdsByPerson === null) return;
      body = { dog_ids: dogIdsByPerson[state.me.person.id] || [] };
    }
    const result = await api(active ? "/api/walks/end" : "/api/walks/start", {
      method: "POST",
      ...(body ? {
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body),
      } : {}),
    });
    toast(active ? "Gassi-Runde beendet" : `Gassi-Runde gestartet (${SLOT_LABELS[result.active.slot]})`);
    await loadGamification();
  } catch (e) { toast(e.message); }
};
document.getElementById("groupWalkConfirmButton").onclick = confirmGroupWalk;
document.getElementById("groupWalkCancelButton").onclick = () => {
  document.getElementById("groupWalkDialog").close();
};
document.getElementById("groupWalkDialog").addEventListener("close", () => {
  groupWalkTarget = null;
});
document.getElementById("dogCareButton").onclick = () => navigateApp("dog-care");
document.getElementById("dogForm").onsubmit = async event => {
  event.preventDefault();
  const name = document.getElementById("dogName").value.trim();
  if (!name) {
    toast("Der Hund braucht einen Namen.");
    return;
  }
  const dogId = document.getElementById("dogId").value;
  const body = { name };
  for (const field of DOG_PROFILE_FIELDS) {
    body[field.key] = document.getElementById(field.inputId).value;
  }
  try {
    await api(dogId ? `/api/dogs/${dogId}` : "/api/dogs", {
      method: dogId ? "PATCH" : "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    });
    resetDogForm();
    await loadDogCare();
  } catch (error) { toast(error.message); }
};
document.getElementById("cancelDogEdit").onclick = resetDogForm;
document.getElementById("dogShareToggleButton").onclick = async () => {
  try {
    if (state.dogShare?.enabled) {
      if (!confirm("Freigabe widerrufen? Der bisherige Link ist danach ungültig.")) return;
      await api("/api/dog-care-share", { method: "DELETE" });
      state.dogShare = { enabled: false, share_url: null };
    } else {
      const result = await api("/api/dog-care-share", { method: "POST" });
      state.dogShare = { enabled: true, ...result };
    }
    renderDogShare();
  } catch (error) { toast(error.message); }
};
document.getElementById("copyDogShareUrl").onclick = async () => {
  const url = document.getElementById("dogShareUrl").value;
  try {
    if (!navigator.clipboard?.writeText) throw new Error("Clipboard nicht verfügbar");
    await navigator.clipboard.writeText(url);
    toast("Link kopiert");
  } catch {
    document.getElementById("dogShareUrl").select();
    toast("Link markieren und kopieren");
  }
};
document.getElementById("dogSelectionConfirmButton").onclick = confirmDogSelections;
document.getElementById("dogSelectionCancelButton").onclick = () => {
  document.getElementById("dogSelectionDialog").close();
};
document.getElementById("dogSelectionDialog").addEventListener("close", () => {
  if (!dogSelectionResolver) return;
  const resolve = dogSelectionResolver;
  dogSelectionResolver = null;
  resolve(null);
});
document.getElementById("takeoverApprovalConfirmButton").onclick = confirmTakeoverApproval;
document.getElementById("takeoverApprovalCancelButton").onclick = () => {
  document.getElementById("takeoverApprovalDialog").close();
};
document.getElementById("takeoverApprovalDialog").addEventListener("close", () => {
  takeoverApprovalTarget = null;
});

function setAuthMode(mode) {
  authMode = mode;
  const registering = mode === "register";
  document.getElementById("authTitle").textContent = registering ? "Konto erstellen" : "Anmelden";
  document.getElementById("authMessage").textContent = registering
    ? "Lege ein Konto mit dem Gruppeneinladungscode an."
    : "Melde dich mit deinem Namen und Passwort an.";
  document.getElementById("inviteLabel").hidden = !registering;
  document.getElementById("password").autocomplete = registering ? "new-password" : "current-password";
  document.getElementById("authSubmit").textContent = registering ? "Konto erstellen" : "Anmelden";
  document.getElementById("loginMode").classList.toggle("active", !registering);
  document.getElementById("registerMode").classList.toggle("active", registering);
}

document.getElementById("loginMode").onclick = () => setAuthMode("login");
document.getElementById("registerMode").onclick = () => setAuthMode("register");

document.getElementById("authForm").onsubmit = async (ev) => {
  ev.preventDefault();
  const registering = authMode === "register";
  const payload = {
    display_name: document.getElementById("displayName").value.trim(),
    password: document.getElementById("password").value,
  };
  if (registering) payload.invite_code = document.getElementById("inviteCode").value;
  try {
    await api(registering ? "/auth/register" : "/auth/login", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
    location.reload();
  } catch (e) { toast(e.message); }
};

document.getElementById("adminUserSelect").onchange = (ev) => {
  state.adminUserId = Number(ev.target.value);
  document.getElementById("adminTakeoverPerson").value = String(state.adminUserId);
  renderAdminPrefs();
};
document.getElementById("adminCompletionKind").onchange = renderAdminCompletionKind;
document.getElementById("adminCompletionForm").onsubmit = submitAdminCompletion;
document.getElementById("refreshActivity").onclick = () => refreshAdminActivity();
document.getElementById("adminPasswordForm").onsubmit = async (ev) => {
  ev.preventDefault();
  if (!state.adminUserId) return;
  const user = state.adminData.users.find(item => item.id === state.adminUserId);
  if (!user || !confirm(`Passwort für ${user.name} zurücksetzen?`)) return;
  try {
    await api(`/api/admin/users/${user.id}/password`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ new_password: document.getElementById("adminNewPassword").value }),
    });
    ev.target.reset();
    toast(`Passwort für ${user.name} zurückgesetzt.`);
  } catch (e) { toast(e.message); }
};

document.getElementById("passwordForm").onsubmit = async (ev) => {
  ev.preventDefault();
  try {
    await api("/api/me/password", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        current_password: document.getElementById("currentPassword").value,
        new_password: document.getElementById("newPassword").value,
      }),
    });
    ev.target.reset();
    toast("Passwort geändert");
  } catch (e) { toast(e.message); }
};

document.getElementById("logoutBtn").onclick = async () => {
  try {
    await api("/auth/logout", { method: "POST" });
    location.reload();
  } catch (e) { toast(e.message); }
};

document.getElementById("newsLaterButton").onclick = () => {
  document.getElementById("newsDialog").close();
};

async function loadNews() {
  if (!state.me) return;
  try {
    const { news } = await api("/api/news");
    if (!news.length) return;
    const dialog = document.getElementById("newsDialog");
    const container = document.getElementById("newsItems");
    container.replaceChildren();
    for (const item of news) {
      const article = document.createElement("article");
      article.className = "news-item";
      const title = document.createElement("h3");
      title.textContent = item.title;
      const version = document.createElement("p");
      version.className = "news-version";
      version.textContent = `Version ${item.version}`;
      const body = document.createElement("p");
      body.textContent = item.body;
      const readButton = document.createElement("button");
      readButton.type = "button";
      readButton.textContent = "Als gelesen markieren";
      readButton.onclick = async () => {
        readButton.disabled = true;
        try {
          await api(`/api/news/${encodeURIComponent(item.id)}/read`, { method: "POST" });
          article.remove();
          if (!container.childElementCount) dialog.close();
        } catch (error) {
          readButton.disabled = false;
          toast(error.message);
        }
      };
      article.append(title, version, body, readButton);
      container.append(article);
    }
    dialog.showModal();
  } catch (error) { toast(error.message); }
}

async function initialize() {
  const auth = document.getElementById("authSection");
  const content = document.getElementById("appContent");
  const nav = document.getElementById("weekNav");
  const accountInfo = document.getElementById("accountInfo");
  try {
    state.me = await api("/api/me");
    auth.hidden = true;
    content.hidden = false;
    nav.hidden = false;
    accountInfo.hidden = false;
    document.getElementById("accountName").textContent = state.me.person.name;
    document.getElementById("adminSection").hidden = !state.me.person.is_admin;
    if (state.me.person.is_admin) loadAdminPanel();
  } catch (e) {
    if (e.status === 401) {
      auth.hidden = false;
      content.hidden = true;
      nav.hidden = true;
      accountInfo.hidden = true;
      return;
    } else if (e.status === 404) {
      state.me = null;
      auth.hidden = true;
      content.hidden = false;
      nav.hidden = false;
      accountInfo.hidden = true;
    } else {
      toast(e.message);
      return;
    }
  }
  if (state.me) loadNews();
  loadWeek()
    .then(async () => {
      await loadGamification();
      if (state.me) {
        await loadProfile();
      }
      applyAppRoute();
    })
    .catch(e => toast(e.message));
}

setAuthMode("login");
initialize();
