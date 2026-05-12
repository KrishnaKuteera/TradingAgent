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

## Step 3: Add Google Service Account Secrets

Once your app is deployed:

1. Click the **three dots (⋮)** in the top right
2. Select **Settings**
3. Click **Secrets** in the left menu
4. **Paste this entire TOML block** into the secrets editor:

```toml
[gcp_service_account]
type = "service_account"
project_id = "tradeportfolioagent"
private_key_id = "52f42fe31773db6383bb8383f78e3f2fae72a46a"
private_key = "-----BEGIN PRIVATE KEY-----\nMIIEvgIBADANBgkqhkiG9w0BAQEFAASCBKgwggSkAgEAAoIBAQDdRvRDs04L0iSv\nH3jdw93ivUhyNs72IoklKq8V0NTQVQZ6WZG9g0VDzkNQyzmqKwrltqMQ5HkmpcE6\n4CVV0n4uKR07E40G9huuMtiGkWR0eagfTRKWvc5J04VMS+vn9Q0AEfQYJdvB3ZPa\ncG2feyvzAZ1ZTjELSzwnTqUxFyLZLG5ntHv9m/QXGMIQBVnjJFyp9saJ4OdXSFcS\nQIeRnHdw6aqloPzcgWAt8Zy+xa+8CKFh16MjLW6YtuCMwG/P732NvjWbefU9OfIM\nCGYHCKct7xgignxTLREEv1RwWkDZnP8ANJRLdDLBLOcyo8agC3RfkLk9IxlKdxHV\nYhBtfl+HAgMBAAECggEACcYcM4tWomctD37mvZxaj1GRedl1MmIt/sR90gs5TF2d\nFGxHsMl88hltfHmcZ2BQ6PrGvCJaPiohb6cZpe9PDaZ9r/jVdjl4RxsEj4ti8i1F\nM750/RkhUpmhJywXC0OoWmrwmJOa8iRz5xQ5zaZbN4ojpZ+N570pEkFnsGZ8AMk7\nZEibfdM9pWOFCDsMKVl9XyN3ZfxGILGrwJ/93jzZvgZmicxjuxYVeEKaHUTpWLJo\nS/xaSN/9250OiMt1B2XN76uF3nbIgxPIzekrP45TI7Sh3fNBAjfvMRrJ5b/11nkE\nOACb33WbLj03X48ijSDLHz7P/lHICa/ogRqCE1M2nQKBgQDuDZ2kvReXofZ1ZY2k\nCk3AYQdcxFs0O4veOORLWGlkJndrPI0SPq3NMlo8CM5+Pu28uMU8IqPlzgsEnpS1\nVGCmOmWU2k3jorXJMfSlD5YqH72okDyDNJNV7ZeY8nwiaAsSrxkg0rWJC+yA8yv/\nXHx++nBVO24/81x5q9+PMWbzswKBgQDt9ZBqGQd+YTvvAprY878+fqRis3dgNbWs\ncy1vUyeeVYUD+8wxdhdkdfwyxIRlBiTeMffuGqhvMw6qaeRW1fDFrCUN6N2uABbN\nJyTqPuvhMU8uccaET+hyHzX4YCwkbnmcoqWUEqRqvlGlmylW6mxqTw4gbkYablxX\nZsmo/QMK3QKBgQDKwfYftp89m8nbvB+kNNJ8pSgsL2KvXniHUlXAhxFdKBZW1EAj\n5hcKy3Rn5ehbRyYetBHqYmbO+WwRBzEKMVAQxXR4EGh/FrtXHqGNZXU1c8uKoy+n\nYUSMz81rjD2G4K9tvo3ckxvkGq/aNUSoQBIZ5R2Auxnwhkuhpm7H/AAAWQKBgGJA\npqRoOUPhehGyDaXO3wQ63j0yxPOguaa+19/DgfRKc2W1rhYuIHKGlN+RbOkZpFdq\nYmiZ8ToY5tFOb827AHNeJN6dbArQVpnWs9NUr6iH553RtJolNGEKqgooC5HvW59l\nOODu4ZyBgMzUSDlvCdzLT5Xscl2ve8lK07FG5t6xAoGBAKk29sgHLo7Z6Gqeo7Dl\n0+6HfPU9KFhqGSVRx9Dn1C3+G3ZKgYBcxWBaaByD+Qfwp8aez/ziKhdUMjhG+Jr4\nt+obAEt43MtWQZjARcIuq9dhJMIFHR3iKfjhCNMsFqoG2yZi9UVatuKR2WlZC8A3\nYzh1kZYXVpCvgC+eQc9r4Mvp\n-----END PRIVATE KEY-----\n"
client_email = "nandatradingapp@tradeportfolioagent.iam.gserviceaccount.com"
client_id = "115878850202951490125"
auth_uri = "https://accounts.google.com/o/oauth2/auth"
token_uri = "https://oauth2.googleapis.com/token"
auth_provider_x509_cert_url = "https://www.googleapis.com/oauth2/v1/certs"
client_x509_cert_url = "https://www.googleapis.com/robot/v1/metadata/x509/nandatradingapp%40tradeportfolioagent.iam.gserviceaccount.com"
universe_domain = "googleapis.com"
```

5. Click **Save** at the bottom
6. Your app will **automatically restart** with the secrets loaded

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
