// Shared by every page: API calls, the nav, errors and formatting.
// The pages only display what the API sends. The access rules live in the API.

const el = (id) => document.getElementById(id);

// GET JSON from the API. Not signed in (401): go to the sign-in page, which
// brings you back here afterwards. Any other error throws the API's message.
async function api(path) {
  const response = await fetch(path);
  if (response.status === 401) {
    location.href = "/login?next=" + encodeURIComponent(location.pathname + location.search);
    throw new Error("Taking you to sign in…");
  }
  const data = await response.json();
  if (!response.ok) throw new Error(data.error);
  return data;
}

// POST a form to the API as JSON (sign in, sign up).
async function post(path, form) {
  const response = await fetch(path, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(Object.fromEntries(new FormData(form))),
  });
  const data = await response.json();
  if (!response.ok) throw new Error(data.error);
  return data;
}

// Runs a page's code. Any error (bad filters, unknown visit) is shown in the
// page's red box rather than leaving a blank screen.
function run(pageCode) {
  pageCode()
    .catch((e) => showError(e.message))
    .finally(() => el("loading")?.remove());
}

function showError(message) {
  el("error").textContent = message;
  el("error").hidden = false;
}

// Every signed-in page starts here: who am I, then draw the nav for my role.
// A viewer is never offered the Users link.
async function signedIn() {
  const me = await api("/api/me");
  document.querySelector("nav").innerHTML = `
    <a class="brand" href="/visits">The Front Desk</a>
    <a href="/visits">Visits</a>
    ${me.role === "admin" ? '<a href="/admin/users">Users</a>' : ""}
    <span class="who">${esc(me.name)} (${me.role}) · <a href="#" onclick="signOut()">Sign out</a></span>`;
  return me;
}

async function signOut() {
  await fetch("/auth/logout", { method: "POST" });
  location.href = "/login";
}

// Where to go after signing in: the page that sent you here, or /visits.
// Only paths on this site, so a crafted link can't send someone elsewhere.
function nextPage() {
  const next = new URLSearchParams(location.search).get("next");
  return next && next.startsWith("/") && !next.startsWith("//") ? next : "/visits";
}

// Names and companies come from a CSV export, so escape them before
// putting them into HTML.
function esc(text) {
  const replacements = { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" };
  return String(text ?? "").replace(/[&<>"]/g, (c) => replacements[c]);
}

// --- Formatting ---------------------------------------------------------------

// "2026-08-31" -> "Mon 31 Aug"
function formatDate(isoDate) {
  return new Date(isoDate + "T00:00").toLocaleDateString("en-GB", {
    weekday: "short", day: "numeric", month: "short",
  });
}

// 9 -> "9am", 13 -> "1pm"
function formatHour(hour) {
  return (hour % 12 || 12) + (hour < 12 ? "am" : "pm");
}

// "2026-08-31 09:53:00" -> "9:53am"
function formatTime(timestamp) {
  const hour = Number(timestamp.slice(11, 13));
  const minutes = timestamp.slice(14, 16);
  return `${hour % 12 || 12}:${minutes}${hour < 12 ? "am" : "pm"}`;
}

function formatSignedOut(visit) {
  return visit.signed_out_at ? formatTime(visit.signed_out_at) : "Didn't sign out";
}

function capitalize(word) {
  return word[0].toUpperCase() + word.slice(1);
}
