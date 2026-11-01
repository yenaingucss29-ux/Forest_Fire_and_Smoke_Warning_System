# Deploy to Railway (screenshare checklist)

The app goes into **the professor's Railway account**, but the files are on **your Mac**. So on the call:

- **You** run the commands in your terminal.
- **The professor** approves the sign-in on his own computer and types the secret values into his Railway dashboard.

Nobody has to share a password. Takes about 15 minutes, most of it waiting for the first build.

---

## Before the call (you)

- [ ] The Railway CLI works: `railway --version` (already installed on this Mac).
- [ ] The app runs locally: `.venv/bin/python -m uvicorn app:app`, then open http://127.0.0.1:8000.
- [ ] You have a **Resend API key** and know **which email address it was signed up with**. Alerts can only go to that address (see the README).
- [ ] You've picked an **admin password** for the `/admin` dashboard, e.g. three random words. Use plain letters and numbers.
- [ ] A **smoke photo** and a **forest photo without smoke** are ready for testing.
- [ ] Ask the professor which Railway plan he's on:
  - **Hobby ($5/month):** fine.
  - **Trial:** fine for 30 days, but his account must be **verified with GitHub** (railway.com/verify). An unverified "Limited Trial" blocks outgoing internet, so the alert emails would fail.

## On the call

### 1. Sign in to the professor's account from your terminal

```bash
cd ~/School/Python_Coding/smoke_webapp
railway login --browserless
```

It prints a **link and a short code**. The professor opens the link on **his** computer, signs in to Railway and confirms the code. Then check:

```bash
railway whoami      # should show the professor's account
```

### 2. Create the project and deploy

```bash
railway up --new --name forest-smoke-warning
```

- If it asks for a workspace, pick the professor's.
- It uploads about 25 MB (the app, `model/best.pt`, `vendor/ultralytics`) and builds the Docker image. The **first build takes about 3–5 minutes** because it downloads PyTorch.
- It's done when the logs show `Uvicorn running on http://0.0.0.0:...`. You can press Ctrl+C then; the app keeps running on Railway.
- `.env` and `.venv` are **not** uploaded (`.railwayignore`), so your API key never leaves your Mac.

### 3. Get the public link

```bash
railway domain
```

It prints something like `https://forest-smoke-warning-production-xxxx.up.railway.app`. Open it: the page works now, but the top-right says "Email alerts not set up". That's the next step.

### 4. Add the secrets (professor, in his dashboard)

The professor opens **railway.com → forest-smoke-warning → the service → Variables → Raw Editor**, pastes this with the real values, and clicks **Update Variables**, then **Deploy** if Railway asks:

```
RESEND_API_KEY=re_...
ALERT_EMAIL_TO=the-email-the-resend-account-was-signed-up-with@example.com
ALERT_EMAIL_FROM=Smoke Alert <onboarding@resend.dev>
ADMIN_PASSWORD=your-admin-password
CONFIDENCE_THRESHOLD=0.30
```

`CONFIDENCE_THRESHOLD` is optional (0.30 is the default). Day to day, change the threshold from the `/admin` dashboard instead; this variable is what its "Reset" button goes back to.

Railway redeploys in about a minute. Doing this in the dashboard keeps the key off your terminal screen.

### 5. (Optional) Keep the settings after redeploys

Without this, the dashboard settings (no-smoke toggle, threshold, email cooldown) go back to their defaults on every redeploy:

```bash
railway volume add --mount-path /app/data
```

### 6. Test it together

- [ ] Top-right shows **"Email alerts on · x***@..."**.
- [ ] Upload the smoke photo: red **SMOKE DETECTED** banner and **"📧 Email sent"**. The email arrives (check spam).
- [ ] Open **`/admin`** (link at the bottom of the page). A wrong password is refused; the right one opens the dashboard.
- [ ] **Recent detections** lists your test upload, and the status cards count it.
- [ ] **Send test email** says "✓ Email sent" and the test email arrives.
- [ ] Turn on **"Alert when no smoke is found"**, upload the no-smoke photo on the main page: green **All clear** banner and an all-clear email. Turn it back off.

### 7. Sign out of the professor's account

```bash
railway logout
```

Don't skip this. Until you log out, your terminal can change anything in his Railway account.

---

## Updating the app later

After changing the code (or copying in a new `best.pt`, see the README), deploy again from this folder:

- **Simplest:** repeat step 1 (sign-in), then run `railway up` (this folder remembers the project), then `railway logout`.
- **Without signing in each time:** the professor creates a **project token** (project → Settings → Tokens), which only gives access to this one project, and sends it to you. Then:
  ```bash
  RAILWAY_TOKEN=the-token railway up --service <service name from the dashboard>
  ```

## Cost

The app uses about 0.5 GB of RAM, so running all the time costs roughly **$5–8 per month** of Railway usage. That's covered by the Trial's $5 for about the first month, or mostly by Hobby's included $5.

**Serverless** (service → Settings) puts the app to sleep when nobody visits, which cuts the cost. The catch: the first visit after a sleep waits a few seconds while the model loads, and can show one error page. **Turn Serverless off before a live demo.**

## If something goes wrong

| What you see | What to do |
| --- | --- |
| `⚠️ Resend error 403: You can only send testing emails to your own email address` | `ALERT_EMAIL_TO` must be the exact email the Resend account was signed up with. |
| `⚠️ Could not reach Resend` | The Railway account is on the Limited Trial, which blocks outgoing internet. Verify it with GitHub (railway.com/verify) or upgrade to Hobby. |
| `⚠️ Email is not set up` | The variables from step 4 are missing or misspelled. Check the Variables tab, then redeploy. |
| The link shows "Application failed to respond" | Check the logs (`railway logs`, or the Deployments tab) for a Python error. If the app is running, check that the domain's port (service → Settings → Networking) matches the port in `Uvicorn running on http://0.0.0.0:<port>`. |
| The deploy crashes with "Killed" or out of memory | The service needs at least 1 GB of memory (service → Settings → Resources). |
| `railway up` says it's not linked, or uses the wrong project | Run `railway link` and pick `forest-smoke-warning`. |
