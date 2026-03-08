# Hannah and Matts Shopping List

A shared web app for you and your partner to manage baby-prep shopping (items with price links), see total spend, and keep to-do lists. Works in the browser and on phones.

---

## Run locally

1. Create a virtual environment (recommended):
   ```bash
   python -m venv venv
   venv\Scripts\activate
   ```
2. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```
3. Start the app:
   ```bash
   python app.py
   ```
4. Open in your browser: **http://localhost:5000**

No login is required when running locally (no password set).

---

## Shared access (same network)

The app binds to `0.0.0.0:5000`, so other devices on your Wi‑Fi can use it too:

1. Find your PC’s IP address (e.g. `ipconfig` on Windows, look for IPv4).
2. On your phone or another computer, open: **http://YOUR_IP:5000**

Both of you see the same data. Refreshing the page loads the latest list.

---

## Deploying so someone in another country/network can open it

To give the app a **public URL** that anyone can open (e.g. your partner abroad), host it on a cloud provider. The app is ready to deploy with **optional shared-password login**.

### 1. Set environment variables (on the host)

| Variable | Required | Description |
|----------|----------|-------------|
| `SHARED_PASSWORD` | **Yes** when deployed | The password you and your partner use to log in. If **not set**, the app has no login (only use when not on the public internet). |
| `SECRET_KEY` | Recommended | A long random string for session cookies (e.g. `openssl rand -hex 32`). If not set, a default is used (fine for dev, not for production). |
| `PORT` | Set by host | Railway/Render set this automatically. |

### 2. Deploy to Railway (easy, free tier)

1. Sign up at [railway.app](https://railway.app).
2. **New Project** → **Deploy from GitHub repo**. Connect GitHub and select this repo (you’ll need to push the project to a GitHub repo first).
3. In the project, open **Variables** and add:
   - `SHARED_PASSWORD` = a password you and your partner will use
   - `SECRET_KEY` = a long random string (e.g. from [randomkeygen.com](https://randomkeygen.com))
4. Railway will build and run the app. It uses the **Procfile** (`gunicorn app:app`) and **requirements.txt**.
5. In **Settings** → **Networking** → **Generate Domain**. You’ll get a URL like `https://your-app.up.railway.app`. Share that link; anyone can open it and log in with `SHARED_PASSWORD`.

### 3. Deploy to Render (alternative)

1. Sign up at [render.com](https://render.com).
2. **New** → **Web Service**. Connect your GitHub repo.
3. **Build command:** `pip install -r requirements.txt`  
   **Start command:** `gunicorn app:app`
4. Under **Environment**, add `SHARED_PASSWORD` and `SECRET_KEY`.
5. Create the service. Render gives you a URL like `https://your-app.onrender.com`.

### 4. What you need to do

- **Push the project to a GitHub repository** (if you haven’t already).
- **Choose a host** (e.g. Railway or Render), connect the repo, and add the env vars above.
- **Share the public URL** and the shared password with your partner. They open the URL, enter the password once, and can use the list from any network or country.

The SQLite database (`baby_list.db`) is created on the server. On Railway/Render the filesystem can be ephemeral, so the DB may be reset on redeploy unless you use a persistent volume (Railway) or an external database later. For a simple shared list, redeploying occasionally may be acceptable.

---

## Install on your phone (PWA)

On your phone, open the app URL (local or deployed) in Chrome or Safari. Use **Add to Home Screen** / **Install app**. The app will open full-screen like a native app.

---

## Auth behaviour

- **No `SHARED_PASSWORD` set** (e.g. local): no login; anyone who can reach the app can use it.
- **`SHARED_PASSWORD` set** (e.g. when deployed): a login page is shown. After entering the correct password, the session is stored in a cookie and “Log out” appears in the header.
