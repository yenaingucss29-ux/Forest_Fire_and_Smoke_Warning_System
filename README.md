# Forest Smoke Warning System — Web App

Visitors upload a photo, the project's Enhanced YOLOv8 model (`model/best.pt`) checks it for smoke, and:

- **Smoke found** → red alarm banner + siren sound in the page, and an alert email to the author (with the annotated image attached) through [Resend](https://resend.com).
- **No smoke found** → shown quietly in the result. If **"Alert when no smoke is found"** is turned on, the page also shows a green "All clear" banner and sends an "all clear" email.

The public page only has upload and result. Everything else is on the **admin dashboard at `/admin`** (linked at the bottom of the page), protected by `ADMIN_PASSWORD`:

- **Status:** model online, email alerts on/off, checks today (smoke / clear), emails sent today against Resend's 100/day.
- **Detection:** the confidence threshold slider. `CONFIDENCE_THRESHOLD` in `.env` is the default (0.30, the best F1 score on the validation set, `ultralytics/runs/detect/val2/F1_curve.png`); "Reset" goes back to it.
- **Alerts:** the "Alert when no smoke is found" toggle, an email cooldown (wait N minutes before another email of the same kind), and a "Send test email" button.
- **Recent detections:** the last 10 checked photos (boxed versions) with time, result, confidence and whether the email went out. Click a thumbnail to see it full size.

The toggle, threshold and cooldown are saved in `data/settings.json`, so they survive restarts. The counts, recent photos and cooldown timers are kept in memory only, never on disk, so a restart clears them. Signing in sets a cookie for 7 days; changing `ADMIN_PASSWORD` signs everyone out. **Without `ADMIN_PASSWORD`, `/admin` is open to anyone** (fine on your own computer only).

**Deploying:** see [DEPLOY_RAILWAY.md](DEPLOY_RAILWAY.md) for the step-by-step Railway checklist.

## How it uses the existing project

- `best.pt` is a YOLOv8s model with two classes: `smoke` and `nonsmoke` (smoke look-alikes such as fog or cloud). Only `smoke` raises the alarm. `nonsmoke` boxes are drawn in grey.
- The model is loaded with the professor's ultralytics fork, which adds the WIoU v4 loss. The fork is imported from its folder rather than pip-installed, because its `pyproject.toml` pins `numpy<=2.1.1`, which can't be installed on Python 3.14.
- So that this folder can be deployed on its own, it holds **copies**: `model/best.pt` (of `../best.pt`) and `vendor/ultralytics/` (of the fork's package, `../ultralytics/ultralytics/`). If the professor retrains or changes the fork, copy them in again:
  ```bash
  cp ../best.pt model/best.pt
  rsync -a --delete --exclude __pycache__ ../ultralytics/ultralytics/ vendor/ultralytics/
  ```

## Setup

```bash
cd smoke_webapp
python3 -m venv --system-site-packages .venv   # reuses torch if it's already installed
.venv/bin/python -m pip install -r requirements.txt
cp .env.example .env                           # then edit .env (see below)
```

### Email alerts (Resend, free plan: 3,000 emails/month, 100/day)

1. Sign up at https://resend.com with the email address that should receive the alerts.
2. Create an API key at https://resend.com/api-keys.
3. Put it in `.env`:
   ```
   RESEND_API_KEY=re_...
   ALERT_EMAIL_TO=the-email-you-signed-up-with@example.com
   ALERT_EMAIL_FROM=Smoke Alert <onboarding@resend.dev>
   ADMIN_PASSWORD=your-long-password
   ```

`ADMIN_PASSWORD` protects `/admin`. It's optional on your own computer but should always be set on a public link.

Until you verify your own domain in Resend, the `onboarding@resend.dev` sender can **only send to the email you signed up with**. That's fine for alerting the author. To email other people, verify a domain in Resend and change `ALERT_EMAIL_FROM`.

Without `.env` the app still works. The page then shows "Email alerts not set up" and skips the email.

## Run

```bash
.venv/bin/python -m uvicorn app:app --reload
```

Open http://127.0.0.1:8000, and http://127.0.0.1:8000/admin for the dashboard. To open it from a phone on the same Wi-Fi, add `--host 0.0.0.0` and use the computer's IP address.

## Files

| File | What it does |
| --- | --- |
| `app.py` | FastAPI server: public page (`/`, `POST /api/detect`, `GET /api/status`) and admin dashboard (`/admin`, `/api/admin/...`) |
| `activity.py` | In-memory recent photos, today's counts and email cooldowns |
| `detector.py` | Loads `best.pt`, runs detection on one frame, draws the boxes |
| `notifier.py` | Sends smoke-alert and all-clear emails through the Resend API |
| `settings_store.py` | Saves the dashboard settings (toggle, threshold, cooldown) to `data/settings.json` |
| `static/` | The public page (`index.html`, `app.js`) and dashboard (`admin.html`, `admin.js`); no build step |
| `model/best.pt` | Copy of the trained model |
| `vendor/ultralytics/` | Copy of the professor's ultralytics fork (AGPL-3.0, licence included) |
| `Dockerfile` | CPU-only container image, used by Railway |
| `DEPLOY_RAILWAY.md` | Screenshare checklist for deploying to Railway |

## Next step: video input

`SmokeDetector.detect(frame, conf)` takes a single OpenCV (BGR) frame, so a camera or video file can reuse it as is:

```python
cap = cv2.VideoCapture("rtsp://camera-address/stream")  # or 0 for a webcam, or "video.mp4"
while True:
    ok, frame = cap.read()
    if not ok:
        break
    result = detector.detect(frame, conf=0.30)
    if result.smoke_detected:
        ...  # send the alert through send_alert() in app.py so the dashboard's email cooldown applies
```

For video, set the dashboard's **email cooldown** (e.g. 5–15 min) so a burning area doesn't send an email per frame, and ideally require smoke in several frames in a row before raising the alarm, which cuts false alarms.

## Known limitations

- The model also flags some ordinary photos as smoke (for example the Ultralytics `bus.jpg` scores 0.37 and `zidane.jpg` 0.41). Raise the threshold in `/admin` (e.g. to 0.45) if random photos cause false alarms. Real forest smoke in the validation images mostly scores 0.5–0.8.
- Anyone who can open the page can upload photos, and every smoke upload sends one email, so the Resend free limit of 100/day applies. Turn on the email cooldown in `/admin` if the link is shared widely.
- The `/admin` sign-in has no attempt limit, so use a long `ADMIN_PASSWORD`.
