# Stock Buy Zone Analyzer - Deployment Guide

## Local Development

### Prerequisites
- Python 3.9+
- Service account JSON key from Google Cloud Console

### Setup

1. **Install dependencies:**
   ```bash
   pip install -r requirements.txt
   ```

2. **Add your service account credentials:**
   - Copy `tradeportfolioagent-52f42fe31773.json` to this directory
   - OR create `.streamlit/secrets.toml` with your credentials (see `.streamlit/secrets.toml.example`)

3. **Run locally:**
   ```bash
   streamlit run dashboard.py
   ```

4. **Access:**
   - Open `http://localhost:8501`

---

## Cloud Deployment on Streamlit Cloud

### Step 1: Prepare Your Repository

```bash
# Initialize git
git init
git add dashboard.py app.py requirements.txt .gitignore DEPLOYMENT.md
git commit -m "Add Stock Buy Zone Analyzer"

# Create a new GitHub repository and push
git remote add origin https://github.com/YOUR_USERNAME/stock-analyzer.git
git branch -M main
git push -u origin main
```

**DO NOT commit** `tradeportfolioagent-52f42fe31773.json` (it will be ignored by `.gitignore`)

### Step 2: Add Secrets to Streamlit Cloud

1. Go to https://share.streamlit.io
2. Click "New app" and select your GitHub repository
3. After deployment, go to **Settings** → **Secrets**
4. Copy your service account JSON and add:

   ```toml
   [gcp_service_account]
   type = "service_account"
   project_id = "your-project-id"
   private_key_id = "your-private-key-id"
   private_key = "your-private-key"
   client_email = "your-service-account-email"
   client_id = "your-client-id"
   auth_uri = "https://accounts.google.com/o/oauth2/auth"
   token_uri = "https://oauth2.googleapis.com/token"
   auth_provider_x509_cert_url = "https://www.googleapis.com/oauth2/v1/certs"
   client_x509_cert_url = "your-cert-url"
   ```

### Step 3: Deploy

1. Go to https://share.streamlit.io
2. Click "New app"
3. Select:
   - GitHub repository
   - Branch: `main`
   - File path: `dashboard.py`
4. Click "Deploy"
5. Wait 2-3 minutes for deployment
6. Get your public shareable URL!

---

## Troubleshooting

**"Service account credentials not found"**
- Ensure secrets are added to Streamlit Cloud settings
- For local dev, ensure JSON file exists in directory

**"Authentication error"**
- Verify Google Sheets API and Google Drive API are enabled
- Check service account has access to "Copy of StockTracker" sheet

**"No tickers found"**
- Verify sheet name is exactly "Copy of StockTracker"
- Check tickers are in column A starting from row 2

---

## Files

- `dashboard.py` - Main Streamlit app
- `app.py` - Original analysis script (for reference)
- `requirements.txt` - Python dependencies
- `.gitignore` - Prevents credentials from being committed
- `tradeportfolioagent-52f42fe31773.json` - Service account key (local only, not in repo)

---

## Security

✅ Service account credentials are managed by Streamlit Secrets (never in git)
✅ Google Sheets API credentials are protected
✅ No sensitive data in the repository

---

## Support

For issues with Streamlit Cloud:
- https://docs.streamlit.io/deploy/streamlit-cloud

For Google Sheets API:
- https://developers.google.com/sheets/api
