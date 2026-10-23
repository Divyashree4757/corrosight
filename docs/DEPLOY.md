# Deploying CorroSight to Streamlit Community Cloud

Result: a public link such as `https://corrosight.streamlit.app`, protected by the CorroSight sign-in page.

## What stays out of Git (already in `.gitignore`)

| Kept out | Why |
|---|---|
| `instance/` (user accounts) | Password hashes and lockout state never go into a repository |
| `.streamlit/secrets.toml` | Account seed for the cloud; pasted into Streamlit Cloud instead |
| `outputs/*` (except samples) | Local review logs, audit log and generated reports |
| `data/real_mendeley_raw/`, `data/real_mendeley/real_ILI_large_*.csv` | Large real-data working files (about 120 MB) |
| `.venv/` | Local Python environment |

## 1. Put the project on GitHub

1. On github.com, create a new repository, for example `corrosight`. **Private** is fine. Do not add a README or .gitignore there.
2. In Terminal on the Mac:
   ```bash
   cd ~/Desktop/corrosight
   git init
   git add .
   git commit -m "CorroSight v1.0"
   git branch -M main
   git remote add origin https://github.com/<your-username>/corrosight.git
   git push -u origin main
   ```
   When Git asks for a password, use a GitHub **personal access token** (github.com > Settings > Developer settings >
   Personal access tokens), not your account password.
3. Check on github.com that `instance/` and `.streamlit/secrets.toml` are **not** in the repository.

## 2. Create the app on Streamlit Community Cloud

1. Go to https://share.streamlit.io and sign in with GitHub. Allow access to the repository.
2. Click **Create app** > **Deploy a public app from GitHub**:
   - Repository: `<your-username>/corrosight`
   - Branch: `main`
   - Main file path: `app.py`
   - App URL: choose a name, for example `corrosight`
3. Open **Advanced settings**:
   - Python version: **3.12**
   - Secrets: open `~/Desktop/corrosight/.streamlit/secrets.toml` in TextEdit, copy everything, paste it here.
4. Click **Deploy**. The first build installs the packages from `requirements.txt` and takes a few minutes.

## 3. Sign in

On first start the app finds no accounts file and creates the accounts from the secrets (hashes only), so the
cloud passwords are the same as on the Mac. Sign in with a **username** (for example `engineer`), not a display name.

## Updating the app later

```bash
cd ~/Desktop/corrosight
git add .
git commit -m "describe the change"
git push
```
Streamlit Cloud redeploys automatically after each push.

## Limits of the free cloud deployment

- **Storage is temporary.** Review decisions, snapshots, uploaded data, new users and the audit log are written
  to the app's disk and are lost when the app restarts, redeploys or wakes from sleep. Accounts come back from
  the secrets. For lasting records, use a database (production roadmap phase 6).
- **The app sleeps** after a period without visitors; the first visit then takes about a minute to wake it.
- **Resources are limited.** Use the small real-data file (`real_ILI_section_GW5000-5049.csv`); the 48 MB file is
  not in Git and would be too slow there.
- **Anyone with the link sees the sign-in page.** Only accounts in the secrets can sign in; there is no self-registration.
- **A browser refresh signs the user out** (sessions live in server memory).

## If the build or start fails

- **Package error during build:** check that `requirements.txt` was pushed; then click **Reboot app**.
- **App does not start and logs mention the port:** delete the line `port = 8502` from `.streamlit/config.toml`,
  commit, and push. Locally, use `streamlit run app.py --server.port 8502` instead.
- **"No user accounts are configured" on the sign-in page:** the secrets were not saved; paste them again under
  app > Settings > Secrets, then **Reboot app**.
- **"Invalid username or password":** type the username (for example `engineer`), not the display name.
