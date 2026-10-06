"use strict";

const CATEGORIES = ["Community", "Technology", "Sports", "Arts", "Food", "Nature"];
const DISCOVER_FILTERS = ["All", "Upcoming", ...CATEGORIES];
const ADMIN_FILTERS = [
  { label: "All", status: null },
  { label: "Pending review", status: "PENDING_REVIEW" },
  { label: "Published", status: "PUBLISHED" },
];
const STATUS_LABELS = { PENDING_REVIEW: "Pending review", PUBLISHED: "Published" };
const ROLE_STORAGE_KEY = "venn-demo-role";

const state = {
  role: "visitor",
  organiserId: null,
  discoverFilter: "All",
  adminStatus: null,
  editingId: null,
  openFormOnLoad: false,
};

const $ = (id) => document.getElementById(id);

// ---------------------------------------------------------------------------
// Small helpers. Event text is only ever inserted with textContent / text nodes,
// never as HTML, so titles and descriptions are always rendered as plain text.
// ---------------------------------------------------------------------------

function h(tag, props = {}, ...children) {
  const node = document.createElement(tag);
  for (const [key, value] of Object.entries(props)) {
    if (value == null || value === false) continue;
    if (key === "class") node.className = value;
    else if (key === "text") node.textContent = value;
    else if (key.startsWith("on")) node.addEventListener(key.slice(2), value);
    else node.setAttribute(key, value === true ? "" : value);
  }
  node.append(...children.flat().filter((child) => child != null && child !== false));
  return node;
}

function icon(name) {
  const ns = "http://www.w3.org/2000/svg";
  const svg = document.createElementNS(ns, "svg");
  svg.setAttribute("class", "icon");
  svg.setAttribute("aria-hidden", "true");
  const use = document.createElementNS(ns, "use");
  use.setAttribute("href", `#i-${name}`);
  svg.append(use);
  return svg;
}

const dateFormat = new Intl.DateTimeFormat(undefined, { day: "2-digit", month: "short", year: "numeric" });
const timeFormat = new Intl.DateTimeFormat(undefined, { hour: "2-digit", minute: "2-digit" });
const formatDate = (iso) => dateFormat.format(new Date(iso));
const formatTime = (iso) => timeFormat.format(new Date(iso));
const formatDateTime = (iso) => `${formatDate(iso)}, ${formatTime(iso)}`;

function toLocalInputValue(iso) {
  const d = new Date(iso);
  const pad = (n) => String(n).padStart(2, "0");
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}T${pad(d.getHours())}:${pad(d.getMinutes())}`;
}

const categoryClass = (category) => (CATEGORIES.includes(category) ? `cat-${category}` : "");

let toastTimer;
function toast(message, isError = false) {
  const node = $("toast");
  node.textContent = message;
  node.classList.toggle("error", isError);
  node.hidden = false;
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => { node.hidden = true; }, 5000);
}

// ---------------------------------------------------------------------------
// API client. The demo role travels as headers; the server enforces permissions.
// ---------------------------------------------------------------------------

class ApiError extends Error {
  constructor(status, code, message, fields) {
    super(message);
    this.status = status;
    this.code = code;
    this.fields = fields || {};
  }
}

async function api(path, { method = "GET", body } = {}) {
  const headers = { Accept: "application/json", "X-Demo-Role": state.role };
  if (state.role === "organiser") headers["X-Demo-Organiser-Id"] = state.organiserId;
  if (body !== undefined) headers["Content-Type"] = "application/json";

  let response;
  try {
    response = await fetch(`/api${path}`, {
      method,
      headers,
      body: body === undefined ? undefined : JSON.stringify(body),
    });
  } catch {
    throw new ApiError(0, "NETWORK_ERROR", "Can't reach the server. Is the backend running?");
  }

  let data = null;
  try { data = await response.json(); } catch { /* non-JSON body */ }
  if (!response.ok) {
    throw new ApiError(response.status, data?.code ?? "ERROR", data?.message ?? "Something went wrong.", data?.fields);
  }
  return data;
}

// ---------------------------------------------------------------------------
// Role + routing
// ---------------------------------------------------------------------------

function setRole(value) {
  const [role, organiserId] = value.split(":");
  state.role = role;
  state.organiserId = organiserId ?? null;
  $("role-select").value = value;
  try { localStorage.setItem(ROLE_STORAGE_KEY, value); } catch { /* storage unavailable */ }
  for (const link of document.querySelectorAll("[data-role]")) {
    link.hidden = link.dataset.role !== role;
  }
  $("hero-create").hidden = role !== "organiser"; // only Organisers see create actions
}

function currentView() {
  const requested = location.hash.match(/^#\/(\w+)/)?.[1] ?? "discover";
  const allowed = {
    discover: true,
    about: true,
    organiser: state.role === "organiser",
    admin: state.role === "admin",
  };
  return allowed[requested] ? requested : "discover";
}

function navigate(view) {
  const target = `#/${view}`;
  if (location.hash === target) render();
  else location.hash = target;
}

async function render() {
  const view = currentView();
  for (const section of document.querySelectorAll(".view")) {
    section.hidden = section.id !== `view-${view}`;
  }
  for (const link of document.querySelectorAll(".main-nav a")) {
    if (link.dataset.view === view) link.setAttribute("aria-current", "page");
    else link.removeAttribute("aria-current");
  }
  // Only Organisers get a header "New event" button, and not on the page that has its own.
  $("header-create").hidden = state.role !== "organiser" || view === "organiser";
  try {
    if (view === "discover") await renderDiscover();
    else if (view === "organiser") await renderOrganiser();
    else if (view === "admin") await renderAdmin();
  } catch (err) {
    toast(err.message, true);
  }
}

function renderChips(container, labels, isSelected, onSelect) {
  container.replaceChildren(
    ...labels.map((label) =>
      h("button", {
        class: "chip",
        type: "button",
        "aria-pressed": String(isSelected(label)),
        text: label,
        onclick: () => onSelect(label),
      })
    )
  );
}

// ---------------------------------------------------------------------------
// Discover (Visitor)
// ---------------------------------------------------------------------------

let discoverRequest = 0;

async function renderDiscover() {
  renderChips($("chips"), DISCOVER_FILTERS, (label) => label === state.discoverFilter, (label) => {
    state.discoverFilter = label;
    renderDiscover().catch((err) => toast(err.message, true));
  });

  const query = new URLSearchParams();
  if (state.discoverFilter === "Upcoming") query.set("upcoming", "true");
  else if (state.discoverFilter !== "All") query.set("category", state.discoverFilter);

  const requestId = ++discoverRequest;
  const { events } = await api(`/events?${query}`);
  if (requestId !== discoverRequest) return; // a newer filter click superseded this one

  $("event-grid").replaceChildren(...events.map(eventCard));
  $("discover-empty").hidden = events.length > 0;
}

const hasStarted = (event) => new Date(event.starts_at) <= new Date();

// Why registration is not possible right now (the server enforces this too), or null if it is.
function registrationBlocker(event) {
  if (hasStarted(event)) return { label: "Registration closed", note: "This event has already started, so registration is closed." };
  if (event.spots_remaining === 0) return { label: "Event full", note: "This event is full." };
  return null;
}

function eventMeta(event) {
  const flag = hasStarted(event) ? "Started" : event.spots_remaining === 0 ? "Full" : null;
  return h("ul", { class: "meta" },
    h("li", {}, icon("calendar"), formatDate(event.starts_at), h("span", { class: "sep" }, "·"), icon("clock"), formatTime(event.starts_at)),
    h("li", {}, icon("users"), `${event.registration_count} / ${event.capacity} spots`,
      flag && h("span", { class: "full-flag", text: flag })),
    h("li", {}, icon("user"), `Organiser: ${event.organiser_id}`)
  );
}

function eventCard(event) {
  return h("article", { class: "card" },
    h("div", { class: `card-banner ${categoryClass(event.category)}`, "aria-hidden": "true" }),
    h("div", { class: "card-body" },
      h("span", { class: `tag ${categoryClass(event.category)}`, text: event.category }),
      h("h3", { text: event.title }),
      h("p", { class: "desc", text: event.description || "No description yet." }),
      eventMeta(event),
      h("button", { class: "btn btn-sm", type: "button", onclick: () => openEventDialog(event.id) },
        "View Event", icon("arrow"))
    )
  );
}

async function openEventDialog(eventId) {
  let event;
  try {
    event = (await api(`/events/${encodeURIComponent(eventId)}`));
  } catch (err) {
    toast(err.message, true);
    return;
  }
  showEventDialog(event);
  $("event-dialog").showModal();
}

function showEventDialog(event) {
  const result = h("div", { "aria-live": "polite" });
  const button = h("button", { class: "btn btn-primary", type: "button" }, "Register interest");
  const blocker = registrationBlocker(event);
  if (blocker) {
    button.disabled = true;
    button.textContent = blocker.label;
  }

  button.addEventListener("click", async () => {
    button.disabled = true;
    try {
      const registration = await api(`/events/${encodeURIComponent(event.id)}/registrations`, { method: "POST" });
      result.replaceChildren(
        h("div", { class: "notice notice-success" }, "You’re registered. Your reference is ", h("code", { text: registration.id }), ".")
      );
      const refreshed = await api(`/events/${encodeURIComponent(event.id)}`);
      $("dialog-body").replaceChildren(...dialogContent(refreshed, result, button));
      const after = registrationBlocker(refreshed);
      button.disabled = Boolean(after);
      if (after) button.textContent = after.label;
      renderDiscover().catch(() => {});
    } catch (err) {
      result.replaceChildren(h("div", { class: "notice notice-error", role: "alert", text: err.message }));
      const closedLabels = { EVENT_FULL: "Event full", EVENT_NOT_PUBLISHED: "Not available", REGISTRATION_CLOSED: "Registration closed" };
      button.disabled = err.code in closedLabels;
      if (button.disabled) button.textContent = closedLabels[err.code];
    }
  });

  $("dialog-body").replaceChildren(...dialogContent(event, result, button));
}

function dialogContent(event, result, button) {
  return [
    h("div", { class: `dialog-banner ${categoryClass(event.category)}`, "aria-hidden": "true" }),
    h("div", { class: "dialog-content" },
      h("span", { class: `tag ${categoryClass(event.category)}`, text: event.category }),
      h("h3", { id: "dialog-title", text: event.title }),
      h("p", { class: "description", text: event.description || "No description yet." }),
      eventMeta(event),
      h("p", { class: "muted", text: registrationBlocker(event)?.note
        ?? `${event.spots_remaining} spot${event.spots_remaining === 1 ? "" : "s"} left. Registering is anonymous.` }),
      result,
      button
    ),
  ];
}

// ---------------------------------------------------------------------------
// Event tables (Organiser + Administrator)
// ---------------------------------------------------------------------------

function statusBadge(status) {
  return h("span", { class: `status status-${status}`, text: STATUS_LABELS[status] ?? status });
}

function eventTable(events, { admin, emptyText }) {
  if (events.length === 0) return h("p", { class: "empty", text: emptyText });

  const columns = ["Event", "Date", admin && "Organiser", "Registered", "Status", ""].filter((c) => c !== false);
  const rows = events.map((event) =>
    h("tr", {},
      h("td", {}, h("span", { class: "title", text: event.title }), h("span", { class: "id", text: event.id })),
      h("td", { text: formatDateTime(event.starts_at) }),
      admin && h("td", { text: event.organiser_id }),
      h("td", { text: `${event.registration_count} / ${event.capacity}` }),
      h("td", {}, statusBadge(event.status)),
      h("td", { class: "actions" }, rowActions(event, admin))
    )
  );
  return h("div", { class: "table-wrap" },
    h("table", {},
      h("thead", {}, h("tr", {}, columns.map((c) =>
        c ? h("th", { scope: "col", text: c }) : h("th", { scope: "col" }, h("span", { class: "sr-only", text: "Actions" }))))),
      h("tbody", {}, rows)
    )
  );
}

function rowActions(event, admin) {
  if (!admin) {
    return h("button", { class: "btn btn-outline btn-sm", type: "button", onclick: () => openForm(event) }, "Edit");
  }

  const actions = [];

  if (event.status === "PENDING_REVIEW") {
    actions.push(
      h("button", {
        class: "btn btn-primary btn-sm",
        type: "button",
        onclick: (e) => publish(event, e.currentTarget)
      }, "Publish")
    );
  }

  actions.push(
    h("button", {
      class: "btn btn-danger btn-sm",
      type: "button",
      onclick: () => deleteEvent(event)
    }, "Delete")
  );

  return h("div", { class: "actions-group" }, ...actions);
}

// ---------------------------------------------------------------------------
// Organiser
// ---------------------------------------------------------------------------

// Opens the create form (only Organisers are ever shown the buttons that call this).
function startCreateEvent() {
  state.openFormOnLoad = true;
  navigate("organiser");
}

async function renderOrganiser() {
  const { events } = await api("/organiser/events");
  $("organiser-list").replaceChildren(
    eventTable(events, { admin: false, emptyText: "You haven’t created any events yet." })
  );
  if (state.openFormOnLoad) {
    state.openFormOnLoad = false;
    openForm();
  }
}

function openForm(event = null) {
  const form = $("event-form");
  clearFormErrors();
  form.reset();
  state.editingId = event?.id ?? null;
  $("form-title").textContent = event ? `Edit ${event.id}` : "Create an event";
  $("form-submit").textContent = event ? "Save changes" : "Submit for review";
  $("f-title").value = event?.title ?? "";
  $("f-description").value = event?.description ?? "";
  $("f-category").value = event?.category ?? "Community";
  $("f-starts-at").value = event ? toLocalInputValue(event.starts_at) : "";
  $("f-capacity").value = event?.capacity ?? 20;
  form.hidden = false;
  const reduceMotion = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
  form.scrollIntoView({ behavior: reduceMotion ? "auto" : "smooth", block: "start" });
  $("f-title").focus({ preventScroll: true });
}

function closeForm() {
  $("event-form").hidden = true;
  state.editingId = null;
}

function clearFormErrors() {
  $("form-error").hidden = true;
  for (const node of document.querySelectorAll(".field-error")) node.textContent = "";
  for (const node of document.querySelectorAll(".field.invalid")) node.classList.remove("invalid");
}

function showFormErrors(err) {
  $("form-error").textContent = err.message;
  $("form-error").hidden = false;
  for (const [field, message] of Object.entries(err.fields)) {
    const target = document.querySelector(`.field-error[data-for="${field}"]`);
    if (!target) continue;
    target.textContent = message;
    target.closest(".field").classList.add("invalid");
  }
}

function formBody() {
  const startsAt = $("f-starts-at").value;
  const capacity = $("f-capacity").value;
  const parsedDate = new Date(startsAt);
  return {
    title: $("f-title").value,
    description: $("f-description").value,
    category: $("f-category").value,
    // datetime-local has no timezone: convert from the browser's local time to UTC.
    starts_at: startsAt && !Number.isNaN(parsedDate.getTime()) ? parsedDate.toISOString() : startsAt,
    capacity: capacity === "" || Number.isNaN(Number(capacity)) ? capacity : Number(capacity),
  };
}

async function submitForm(submitEvent) {
  submitEvent.preventDefault();
  clearFormErrors();
  const editing = state.editingId;
  const submit = $("form-submit");
  submit.disabled = true;
  try {
    const saved = editing
      ? await api(`/events/${encodeURIComponent(editing)}`, { method: "PUT", body: formBody() })
      : await api("/events", { method: "POST", body: formBody() });
    closeForm();
    toast(editing
      ? `Event ${saved.id} updated.`
      : `Event ${saved.id} submitted. Visitors will see it once an administrator publishes it.`);
    await renderOrganiser();
  } catch (err) {
    if (err instanceof ApiError && err.status === 400) showFormErrors(err);
    else toast(err.message, true);
  } finally {
    submit.disabled = false;
  }
}

// ---------------------------------------------------------------------------
// Administrator
// ---------------------------------------------------------------------------

async function renderAdmin() {
  renderChips($("admin-chips"), ADMIN_FILTERS.map((f) => f.label),
    (label) => ADMIN_FILTERS.find((f) => f.label === label).status === state.adminStatus,
    (label) => {
      state.adminStatus = ADMIN_FILTERS.find((f) => f.label === label).status;
      renderAdmin().catch((err) => toast(err.message, true));
    });

  const query = state.adminStatus ? `?status=${state.adminStatus}` : "";
  const [{ events }, { activity }] = await Promise.all([api(`/admin/events${query}`), api("/admin/activity")]);

  $("admin-list").replaceChildren(eventTable(events, { admin: true, emptyText: "No events in this view." }));
  $("activity-list").replaceChildren(
    ...(activity.length
      ? activity.map((entry) => h("li", {}, h("span", { text: entry.message }), h("time", { datetime: entry.created_at, text: formatDateTime(entry.created_at) })))
      : [h("li", { class: "none", text: "No activity yet." })])
  );
}

async function publish(event, button) {
  button.disabled = true;
  try {
    await api(`/events/${encodeURIComponent(event.id)}/publish`, { method: "POST" });
    toast(`Event ${event.id} published. It is now visible to Visitors.`);
  } catch (err) {
    toast(err.message, true);
  }
  await render();
}

async function deleteEvent(event) {
  const confirmed = window.confirm(
    `Are you sure you want to delete "${event.title}"? This cannot be undone.`
  );

  if (!confirmed) return;

  try {
    await api(`/events/${encodeURIComponent(event.id)}`, { method: "DELETE" });
    toast(`Event ${event.id} deleted.`);
    await render();
  } catch (err) {
    toast(err.message, true);
  }
}

// ---------------------------------------------------------------------------
// Start-up
// ---------------------------------------------------------------------------

function init() {
  $("f-category").replaceChildren(...CATEGORIES.map((c) => h("option", { value: c, text: c })));

  let stored = null;
  try { stored = localStorage.getItem(ROLE_STORAGE_KEY); } catch { /* storage unavailable */ }
  const known = [...$("role-select").options].map((o) => o.value);
  setRole(known.includes(stored) ? stored : "visitor");

  $("role-select").addEventListener("change", (e) => {
    setRole(e.target.value);
    closeForm();
    render();
  });
  $("hero-create").addEventListener("click", startCreateEvent);
  $("header-create").addEventListener("click", startCreateEvent);
  $("new-event").addEventListener("click", () => openForm());
  $("form-cancel").addEventListener("click", closeForm);
  $("event-form").addEventListener("submit", submitForm);
  $("dialog-close").addEventListener("click", () => $("event-dialog").close());
  $("event-dialog").addEventListener("click", (e) => {
    if (e.target === $("event-dialog")) $("event-dialog").close(); // click on the backdrop
  });
  window.addEventListener("hashchange", () => {
    // Plain in-page anchors (e.g. "#events") are not routes.
    if (/^#\/\w+/.test(location.hash) || location.hash === "") render();
  });

  render();
}

document.addEventListener("DOMContentLoaded", init);
