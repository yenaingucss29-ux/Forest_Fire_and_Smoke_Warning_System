const $ = (id) => document.getElementById(id);
const pct = (x) => `${Math.round(x * 100)}%`;

let confidenceDirty = false; // don't overwrite the slider while the admin is moving it

// ---------- Talking to the server ----------

class SignedOut extends Error {}

async function api(path, options = {}) {
  const res = await fetch(path, { ...options, headers: { "Content-Type": "application/json" } });
  if (res.status === 401) {
    showSignIn();
    throw new SignedOut();
  }
  const data = await res.json();
  if (!res.ok) throw new Error(typeof data.detail === "string" ? data.detail : "Request failed.");
  return data;
}

async function refresh() {
  try {
    render(await api("/api/admin/overview"));
  } catch (err) {
    if (!(err instanceof SignedOut)) toast(err.message, true);
  }
}

async function save(changes, message) {
  try {
    render(await api("/api/admin/settings", { method: "PUT", body: JSON.stringify(changes) }));
    toast(message);
  } catch (err) {
    if (err instanceof SignedOut) return;
    toast(err.message, true);
    refresh(); // put the controls back to the saved values
  }
}

// ---------- Sign in / out ----------

function showSignIn() {
  $("dashboard").hidden = true;
  $("signOut").hidden = true;
  $("signIn").hidden = false;
  $("password").focus();
}

$("signIn").addEventListener("submit", async (e) => {
  e.preventDefault();
  const res = await fetch("/api/admin/login", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ password: $("password").value }),
  });
  $("password").value = "";
  $("signInError").textContent = "Wrong password.";
  $("signInError").hidden = res.ok;
  if (res.ok) refresh();
});

$("signOut").addEventListener("click", async () => {
  await fetch("/api/admin/logout", { method: "POST" });
  showSignIn();
});

// ---------- Rendering ----------

function render(o) {
  $("signIn").hidden = true;
  $("dashboard").hidden = false;
  $("signOut").hidden = !o.password_required;
  $("openWarning").hidden = o.password_required;

  $("modelName").textContent = o.model.name;
  $("modelLabels").textContent = o.model.labels.join(" / ");
  $("emailState").textContent = o.email.configured ? "● On" : "○ Off";
  $("emailState").className = o.email.configured ? "ok" : "bad";
  $("emailTo").textContent = o.email.configured ? o.email.to : "Set RESEND_API_KEY and ALERT_EMAIL_TO";
  $("emailTo").title = $("emailTo").textContent;
  $("checks").textContent = o.stats.checks;
  $("checksSmoke").textContent = `${o.stats.smoke} with smoke`;
  $("checksClear").textContent = `${o.stats.clear} clear`;
  $("emails").textContent = `${o.stats.emails_sent} / ${o.email.daily_limit}`;

  const s = o.settings;
  if (!confidenceDirty) $("confidence").value = s.confidence;
  showConfidence();
  $("confidenceSource").textContent = s.confidence_overridden ? "(set here)" : "(from .env)";
  $("confidenceDefault").textContent = s.confidence_default.toFixed(2);
  $("resetConfidence").disabled = !s.confidence_overridden;
  $("notifyNoSmoke").checked = s.notify_no_smoke;
  $("cooldown").value = String(s.email_cooldown_min);
  $("testTo").textContent = o.email.configured ? o.email.to : "the alert address (email isn't set up yet)";
  $("sendTest").disabled = !o.email.configured;

  $("recentEmpty").hidden = o.recent.length > 0;
  $("recentTable").hidden = o.recent.length === 0;
  $("recentRows").replaceChildren(...o.recent.map(recentRow));
}

function showConfidence() {
  $("confidenceValue").textContent = Number($("confidence").value).toFixed(2);
  $("saveConfidence").disabled = !confidenceDirty;
}

function recentRow(p) {
  const img = Object.assign(document.createElement("img"), {
    src: `/api/admin/photos/${p.id}`,
    alt: p.filename,
    className: "thumb",
    loading: "lazy",
  });
  img.addEventListener("click", () => openPhoto(img.src, p.filename));

  const email = p.email ? (p.email.sent ? "✓ Sent" : "✗ Not sent") : "—";
  const cells = [
    img,
    new Date(p.time).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit", second: "2-digit" }),
    p.filename,
    p.smoke_detected ? `▲ Smoke (${p.regions})` : "Clear",
    p.smoke_detected ? pct(p.max_smoke_confidence) : "—",
    email,
  ];
  const tr = document.createElement("tr");
  tr.className = p.smoke_detected ? "smoke" : "";
  for (const cell of cells) {
    const td = document.createElement("td");
    td.append(cell);
    tr.append(td);
  }
  tr.children[2].className = "clip";
  tr.children[2].title = p.filename;
  if (p.email) tr.children[5].title = p.email.detail;
  return tr;
}

function openPhoto(src, name) {
  $("dialogImage").src = src;
  $("dialogImage").alt = name;
  $("photoDialog").showModal();
}

$("photoDialog").addEventListener("click", (e) => e.target === $("photoDialog") && $("photoDialog").close());

function toast(message, isError = false) {
  const el = $("toast");
  el.textContent = message;
  el.classList.toggle("error", isError);
  el.hidden = false;
  clearTimeout(toast.timer);
  toast.timer = setTimeout(() => (el.hidden = true), 2500);
}

// ---------- Controls ----------

$("confidence").addEventListener("input", () => {
  confidenceDirty = true;
  showConfidence();
});
$("saveConfidence").addEventListener("click", () => {
  confidenceDirty = false;
  save({ confidence: Number($("confidence").value) }, "Threshold saved.");
});
$("resetConfidence").addEventListener("click", () => {
  confidenceDirty = false;
  save({ confidence: null }, "Threshold back to the .env default.");
});
$("notifyNoSmoke").addEventListener("change", () => save({ notify_no_smoke: $("notifyNoSmoke").checked }, "Saved."));
$("cooldown").addEventListener("change", () => save({ email_cooldown_min: Number($("cooldown").value) }, "Saved."));
$("refresh").addEventListener("click", refresh);

$("sendTest").addEventListener("click", async () => {
  $("sendTest").disabled = true;
  $("testResult").textContent = "Sending…";
  $("testResult").classList.remove("error");
  try {
    const r = await api("/api/admin/test-email", { method: "POST" });
    $("testResult").textContent = (r.sent ? "✓ " : "✗ ") + r.detail;
    $("testResult").classList.toggle("error", !r.sent);
  } catch (err) {
    if (!(err instanceof SignedOut)) $("testResult").textContent = "✗ " + err.message;
  }
  refresh();
});

// Keep the numbers and recent detections current while the dashboard is open.
setInterval(() => {
  if (!document.hidden && !$("dashboard").hidden) refresh();
}, 15000);

refresh();
