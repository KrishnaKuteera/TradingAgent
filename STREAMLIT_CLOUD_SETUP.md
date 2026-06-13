# 🚀 Streamlit Cloud Deployment Guide

## Step 1: Go to Streamlit Cloud

1. Open https://share.streamlit.io
2. **Sign in with GitHub** (if you don't have an account, create one)

---

## Step 2: Create New App

1. Click **"New app"** button
2. Fill in:
   - **Repository**: `KrishnaKuteera/TradingAgent`
   - **Branch**: `main`
   - **Main file path**: `dashboard.py`
3. Click **Deploy**

Wait 2-3 minutes for deployment to complete...

---

## Step 3: Add Secrets

Once your app is deployed:

1. Click the **three dots (⋮)** in the top right
2. Select **Settings**
3. Click **Secrets** in the left menu
4. Paste the following, filling in your actual values:

```toml
[gcp_service_account]
type = "service_account"
project_id = "tradeportfolioagent"
private_key_id = "YOUR_PRIVATE_KEY_ID"
private_key = "-----BEGIN PRIVATE KEY-----\nYOUR_PRIVATE_KEY\n-----END PRIVATE KEY-----\n"
client_email = "nandatradingapp@tradeportfolioagent.iam.gserviceaccount.com"
client_id = "YOUR_CLIENT_ID"
auth_uri = "https://accounts.google.com/o/oauth2/auth"
token_uri = "https://oauth2.googleapis.com/token"
auth_provider_x509_cert_url = "https://www.googleapis.com/oauth2/v1/certs"
client_x509_cert_url = "https://www.googleapis.com/robot/v1/metadata/x509/nandatradingapp%40tradeportfolioagent.iam.gserviceaccount.com"
universe_domain = "googleapis.com"

[questrade]
chandu_token = "YOUR_CHANDU_QUESTRADE_REFRESH_TOKEN"
# nandu_token = "YOUR_NANDU_QUESTRADE_REFRESH_TOKEN"  # uncomment when ready
```

> ⚠️ **Never paste real keys into this file.** Add them only via the Streamlit Cloud UI.
> Get `chandu_token` from `PortfolioReport/Config/ChanduAPITracker` on your Mac.
> Get the GCP key from Google Cloud Console → Service Accounts → generate a new key (JSON).

5. Click **Save** — app restarts automatically

---

## Step 3b: Repo Structure for Portfolio Tab

The `PortfolioReport/` folder must be inside the GitHub repo alongside `dashboard.py`:

```
KrishnaKuteera/TradingAgent (repo root)
├── dashboard.py
├── requirements.txt
├── PortfolioReport/
│   ├── src/
│   │   ├── questrade_api.py
│   │   ├── config.py, utils.py, calc.py, data.py, report.py
│   └── Config/           ← token files NOT committed (use secrets instead)
└── ...
```

To add `PortfolioReport/` to the repo:
```bash
cd /path/to/TradingAgent-repo
cp -r /Users/nandakumar/Documents/Nanda_Investment/PortfolioReport/src ./PortfolioReport/src
# Do NOT copy Config/ (contains tokens)
git add PortfolioReport/
git commit -m "Add PortfolioReport module for portfolio tab"
git push
```

---

## Step 4: Get Your Public URL

Once deployed, you'll get a URL like:

```
https://tradingagent-xxxxxx.streamlit.app
```

This is your **public shareable link!** 🎉

---

## Step 5: Share with Friends

Send them your Streamlit Cloud URL:

```
https://tradingagent-xxxxxx.streamlit.app
```

They can login with credentials from your **Auth tab** in Google Sheets!

---

## Troubleshooting

**"Service account credentials not found"**
- Go back to **Settings → Secrets**
- Make sure the TOML block is pasted correctly
- Click Save
- Wait for app to restart

**"Auth tab not found"**
- Ensure your Google Sheet has an 'Auth' tab with: username, password, email, name

**"Invalid username or password"**
- Check credentials in your Auth tab
- Make sure password is a bcrypt hash (60 characters, starts with $2b$12$)

**App is slow**
- Data is cached for 5 minutes
- First run takes longer as it fetches all 46 tickers

---

## Your App Features

✅ Login with Google Sheet credentials
✅ 46 stock analysis (50-DMA & VCP patterns)
✅ Interactive charts
✅ Download CSV results
✅ 5-minute caching
✅ Works on any device with a browser

---

## Deployment Complete! 🚀

Once deployed, your Stock Buy Zone Analyzer is live and shareable!

**Share your URL with your friends and they can:**
- Login securely
- View buy zone stocks
- Download analysis
- All without needing to install anything!

---

## Updates

To update your app after making changes:
1. Commit changes locally: `git commit -m "message"`
2. Push to GitHub: `git push`
3. Streamlit Cloud automatically deploys the latest code! (within 1-2 minutes)

---

Need help? See DEPLOYMENT.md for more details.
