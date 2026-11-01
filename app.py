"""Forest smoke warning system — web app.

Visitors upload a photo, the Enhanced YOLOv8 model (best.pt) checks it for smoke, and if smoke is found
the page shows an alarm and an alert email goes to the author through Resend.
The author changes the alert settings and sees recent activity on the password-protected /admin dashboard.

Run:  .venv/bin/python -m uvicorn app:app --reload     then open http://127.0.0.1:8000
"""

import base64
import hashlib
import hmac
import math
import os
from pathlib import Path

import cv2
import numpy as np
from dotenv import load_dotenv
from fastapi import Depends, FastAPI, File, HTTPException, Request, Response, UploadFile
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from activity import Activity
from detector import SmokeDetector
from notifier import EmailNotifier, EmailStatus, mask_email
from settings_store import SettingsStore

APP_DIR = Path(__file__).parent
load_dotenv(APP_DIR / ".env")

MODEL_NAME = "Enhanced YOLOv8"
# Copies of ../best.pt and the professor's ../ultralytics/ultralytics fork, so this folder deploys on its own.
MODEL_PATH = (APP_DIR / os.getenv("MODEL_PATH", "model/best.pt")).resolve()
ULTRALYTICS_DIR = (APP_DIR / os.getenv("ULTRALYTICS_DIR", "vendor")).resolve()
ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD", "")  # protects /admin; without it the dashboard is open to anyone
# Default minimum confidence for a detection to count; the /admin dashboard can override it. 0.30 had the
# best F1 score on the validation set (ultralytics/runs/detect/val2/F1_curve.png).
CONFIDENCE_THRESHOLD = float(os.getenv("CONFIDENCE_THRESHOLD", "0.30"))
if not 0.01 <= CONFIDENCE_THRESHOLD <= 0.99:
    raise ValueError(f"CONFIDENCE_THRESHOLD must be between 0.01 and 0.99, got {CONFIDENCE_THRESHOLD}")
MAX_UPLOAD_BYTES = 15 * 1024 * 1024
MAX_RESULT_SIDE = 1600  # annotated image is shrunk to this before sending to the browser / email
RESEND_DAILY_LIMIT = 100  # Resend free plan
SESSION_COOKIE = "admin_session"

detector = SmokeDetector(MODEL_PATH, ULTRALYTICS_DIR)
notifier = EmailNotifier(
    api_key=os.getenv("RESEND_API_KEY", ""),
    to=os.getenv("ALERT_EMAIL_TO", ""),
    sender=os.getenv("ALERT_EMAIL_FROM", "Smoke Alert <onboarding@resend.dev>"),
)
settings = SettingsStore(APP_DIR / "data" / "settings.json")
activity = Activity()
print(f"Model: {MODEL_PATH} {detector.labels} | ultralytics: {detector.ultralytics_path}")
override = settings.get()["confidence"]
print(f"Confidence threshold: {CONFIDENCE_THRESHOLD} from .env" + (f", set to {override} in /admin" if override is not None else ""))
print(f"Email alerts: {'on, to ' + notifier.to if notifier.configured else 'OFF (set RESEND_API_KEY and ALERT_EMAIL_TO in .env)'}")
print(f"Admin dashboard: /admin {'(password protected)' if ADMIN_PASSWORD else '(OPEN to anyone: set ADMIN_PASSWORD)'}")

app = FastAPI(title="Forest Smoke Warning System")
app.mount("/static", StaticFiles(directory=APP_DIR / "static"), name="static")


# ---------- Public page ----------

@app.get("/")
def index():
    return FileResponse(APP_DIR / "static" / "index.html")


@app.get("/api/status")
def status():
    return {
        "email_configured": notifier.configured,
        "email_to": mask_email(notifier.to) if notifier.configured else None,
    }


@app.post("/api/detect")
def detect(file: UploadFile = File(...)):
    data = file.file.read(MAX_UPLOAD_BYTES + 1)
    if len(data) > MAX_UPLOAD_BYTES:
        raise HTTPException(413, f"Image is too large (max {MAX_UPLOAD_BYTES // 1024 // 1024} MB).")
    frame = cv2.imdecode(np.frombuffer(data, np.uint8), cv2.IMREAD_COLOR)
    if frame is None:
        raise HTTPException(400, "Could not read that file as an image. Use JPG, PNG, BMP or WEBP.")

    current = settings.get()
    result = detector.detect(frame, conf=confidence_threshold(current))
    image_jpeg = encode_jpeg(result.annotated)
    filename = file.filename or "image"
    source = f"Uploaded photo: {filename}"

    # Smoke always raises the alarm. "No smoke" only alerts when the toggle is on.
    if result.smoke_detected:
        email = send_alert("smoke", current, lambda: notifier.send_smoke_alert(result, source, image_jpeg))
    elif current["notify_no_smoke"]:
        email = send_alert("clear", current, lambda: notifier.send_all_clear(source))
    else:
        email = None
    activity.record_check(filename, result, image_jpeg, email)

    return {
        "smoke_detected": result.smoke_detected,
        "alert": result.smoke_detected or current["notify_no_smoke"],
        "max_smoke_confidence": result.max_smoke_confidence,
        "detections": [d.__dict__ for d in result.detections],
        "inference_ms": result.inference_ms,
        "image": "data:image/jpeg;base64," + base64.b64encode(image_jpeg).decode(),
        "email": email.__dict__ if email else None,
    }


# ---------- Admin dashboard ----------

class Login(BaseModel):
    password: str


class AdminSettingsUpdate(BaseModel):
    notify_no_smoke: bool | None = None
    confidence: float | None = Field(None, ge=0.05, le=0.95)  # null = back to CONFIDENCE_THRESHOLD from .env
    email_cooldown_min: int | None = Field(None, ge=0, le=1440)


def session_token() -> str:
    # Derived from the password, so changing ADMIN_PASSWORD signs everyone out.
    return hmac.new(ADMIN_PASSWORD.encode(), b"forest-smoke-admin", hashlib.sha256).hexdigest()


def require_admin(request: Request):
    if ADMIN_PASSWORD and not hmac.compare_digest(request.cookies.get(SESSION_COOKIE, ""), session_token()):
        raise HTTPException(401, "Sign in to the admin dashboard.")


@app.get("/admin")
def admin_page():
    return FileResponse(APP_DIR / "static" / "admin.html")


@app.post("/api/admin/login")
def admin_login(login: Login, request: Request, response: Response):
    if not ADMIN_PASSWORD:
        return {"ok": True}
    if not hmac.compare_digest(login.password.encode(), ADMIN_PASSWORD.encode()):
        raise HTTPException(401, "Wrong password.")
    # Railway serves HTTPS through a proxy, so the app itself sees plain HTTP; trust the forwarded scheme.
    https = request.headers.get("x-forwarded-proto", request.url.scheme) == "https"
    response.set_cookie(SESSION_COOKIE, session_token(), max_age=7 * 24 * 3600,
                        httponly=True, samesite="strict", secure=https)
    return {"ok": True}


@app.post("/api/admin/logout")
def admin_logout(response: Response):
    response.delete_cookie(SESSION_COOKIE)
    return {"ok": True}


@app.get("/api/admin/overview", dependencies=[Depends(require_admin)])
def admin_overview():
    current = settings.get()
    stats, recent = activity.snapshot()
    return {
        "password_required": bool(ADMIN_PASSWORD),
        "model": {"name": MODEL_NAME, "labels": list(detector.labels.values())},
        "email": {"configured": notifier.configured, "to": notifier.to, "daily_limit": RESEND_DAILY_LIMIT},
        "stats": stats,
        "settings": {
            "notify_no_smoke": current["notify_no_smoke"],
            "email_cooldown_min": current["email_cooldown_min"],
            "confidence": confidence_threshold(current),
            "confidence_default": CONFIDENCE_THRESHOLD,
            "confidence_overridden": current["confidence"] is not None,
        },
        "recent": recent,
    }


@app.put("/api/admin/settings", dependencies=[Depends(require_admin)])
def admin_update_settings(update: AdminSettingsUpdate):
    changes = update.model_dump(exclude_unset=True)
    # null only means something for confidence ("use the .env default"), so ignore it elsewhere
    settings.update({k: v for k, v in changes.items() if v is not None or k == "confidence"})
    return admin_overview()


@app.post("/api/admin/test-email", dependencies=[Depends(require_admin)])
def admin_test_email():
    status = notifier.send_test()
    activity.email_sent(None, status)
    return status.__dict__


@app.get("/api/admin/photos/{photo_id}", dependencies=[Depends(require_admin)])
def admin_photo(photo_id: int):
    image = activity.photo(photo_id)
    if image is None:
        raise HTTPException(404, "Only the last 10 photos are kept.")
    return Response(image, media_type="image/jpeg", headers={"Cache-Control": "private, max-age=3600"})


# ---------- Helpers ----------

def confidence_threshold(current: dict) -> float:
    """The value set in /admin, or CONFIDENCE_THRESHOLD from .env if none was set."""
    return current["confidence"] if current["confidence"] is not None else CONFIDENCE_THRESHOLD


def send_alert(kind: str, current: dict, send) -> EmailStatus:
    """Send an alert email unless one of the same kind went out within the cooldown set in /admin."""
    wait = activity.cooldown_left(kind, current["email_cooldown_min"])
    if wait:
        return EmailStatus(False, f"Email skipped: cooldown, the next one can go out in {math.ceil(wait / 60)} min.")
    status = send()
    activity.email_sent(kind, status)
    return status


def encode_jpeg(image: np.ndarray) -> bytes:
    h, w = image.shape[:2]
    if max(h, w) > MAX_RESULT_SIDE:
        ratio = MAX_RESULT_SIDE / max(h, w)
        image = cv2.resize(image, (round(w * ratio), round(h * ratio)), interpolation=cv2.INTER_AREA)
    return cv2.imencode(".jpg", image, [cv2.IMWRITE_JPEG_QUALITY, 88])[1].tobytes()
