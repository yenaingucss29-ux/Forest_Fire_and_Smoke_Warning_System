const $ = (id) => document.getElementById(id);

const fileInput = $("fileInput");
const dropzone = $("dropzone");

// ---------- Email status pill ----------

async function loadStatus() {
  const s = await (await fetch("/api/status")).json();
  const pill = $("emailStatus");
  pill.textContent = s.email_configured ? "● Email alerts on" : "○ Email alerts off";
  pill.className = "pill " + (s.email_configured ? "on" : "off");
}

// ---------- Upload ----------

fileInput.addEventListener("change", () => fileInput.files[0] && checkImage(fileInput.files[0]));

["dragenter", "dragover"].forEach((type) =>
  dropzone.addEventListener(type, (e) => {
    e.preventDefault();
    dropzone.classList.add("dragover");
  })
);
["dragleave", "drop"].forEach((type) =>
  dropzone.addEventListener(type, (e) => {
    e.preventDefault();
    dropzone.classList.remove("dragover");
  })
);
dropzone.addEventListener("drop", (e) => {
  const file = e.dataTransfer.files[0];
  if (file) checkImage(file);
});

async function checkImage(file) {
  $("uploadError").hidden = true;
  $("alert").hidden = true;
  $("result").hidden = true;
  $("resultLoading").hidden = false;

  const form = new FormData();
  form.append("file", file);
  try {
    const res = await fetch("/api/detect", { method: "POST", body: form });
    const data = await res.json();
    if (!res.ok) throw new Error(data.detail || "Detection failed.");
    showResult(data);
    ($("alert").hidden ? $("result") : $("alert")).scrollIntoView({ behavior: "smooth", block: "start" });
  } catch (err) {
    $("uploadError").textContent = err.message;
    $("uploadError").hidden = false;
  } finally {
    $("resultLoading").hidden = true;
    fileInput.value = ""; // allow choosing the same file again
  }
}

// ---------- Result + alarm ----------

function showResult(data) {
  const pct = (x) => `${Math.round(x * 100)}%`;
  const smokeCount = data.detections.filter((d) => d.label === "smoke").length;

  const verdict = $("verdict");
  verdict.textContent = data.smoke_detected
    ? `🔥 Smoke detected — ${smokeCount} region(s)`
    : "✅ No smoke detected";
  verdict.className = "verdict " + (data.smoke_detected ? "smoke" : "clear");

  $("resultImage").src = data.image;
  $("detections").innerHTML = "";
  for (const d of data.detections) {
    const li = document.createElement("li");
    li.className = d.label;
    li.textContent = `${d.label} · ${pct(d.confidence)}`;
    $("detections").append(li);
  }
  $("resultMeta").textContent = `Model time ${Math.round(data.inference_ms)} ms`;
  $("result").hidden = false;

  if (data.alert) showAlert(data);
}

function showAlert(data) {
  const alert = $("alert");
  alert.className = "alert " + (data.smoke_detected ? "smoke" : "clear");
  $("alertTitle").textContent = data.smoke_detected ? "🔥 SMOKE DETECTED" : "✅ All clear";
  $("alertText").textContent = data.smoke_detected
    ? `Possible fire: smoke found with ${Math.round(data.max_smoke_confidence * 100)}% confidence.`
    : "No smoke was found in this photo.";
  $("alertEmail").textContent = data.email
    ? (data.email.sent ? "📧 " : "⚠️ ") + data.email.detail
    : "";
  alert.hidden = false;
  if (data.smoke_detected) playAlarm();
}

$("alertDismiss").addEventListener("click", () => ($("alert").hidden = true));

// Short two-tone siren with the Web Audio API (no sound file needed).
function playAlarm() {
  try {
    const ctx = new AudioContext();
    const osc = ctx.createOscillator();
    const gain = ctx.createGain();
    osc.type = "square";
    gain.gain.value = 0.08;
    for (let i = 0; i < 6; i++) osc.frequency.setValueAtTime(i % 2 ? 660 : 880, ctx.currentTime + i * 0.25);
    osc.connect(gain).connect(ctx.destination);
    osc.start();
    osc.stop(ctx.currentTime + 1.5);
    osc.onended = () => ctx.close();
  } catch {
    // Sound is a bonus; the banner is the real alert.
  }
}

loadStatus();
