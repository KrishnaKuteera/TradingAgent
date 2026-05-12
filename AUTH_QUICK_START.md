# 🔐 Authentication Quick Start

## What Changed

✅ Dashboard now requires **login** before accessing the trading UI
✅ User credentials stored in Google Sheet **'Auth' tab** (not local YAML)
✅ User list **cached for 1 hour** (reduces Google API calls)
✅ Passwords stored as **bcrypt hashes** (secure)
✅ Main dashboard only renders **after successful login**
✅ User info displayed in sidebar with **logout button**

---

## Setup in 5 Minutes

### Step 1: Add Auth Tab to Google Sheet

1. Open your "Copy of StockTracker" Google Sheet
2. Click **"+"** to add a new sheet
3. Name it **'Auth'** (exactly, case-sensitive)

### Step 2: Add Column Headers (Row 1)

In the 'Auth' tab, add these headers in row 1:

```
username | password | email | name
```

### Step 3: Add Test Users

Copy this to rows 2-4 of your Auth tab:

```
demo | $2b$12$BRusIh3AkDk8YqLbsiO1re//LXExfGoItwtIeqbXzqH2/7lHHC.1q | demo@example.com | Demo User
trader1 | $2b$12$dRFjmrlUg96s95sGIo6qoOIYB8FCQDvh2aUN69AriZ1sDL.RQ5WSa | trader1@company.com | Trader One
trader2 | $2b$12$B3J2LQQGrfPVnB8qbiIz.OaIAzLDkoxslIO4T/WkWSwoRH7gXgFii | trader2@company.com | Trader Two
```

### Step 4: Test Login

Start the dashboard:

```bash
streamlit run dashboard.py
```

Login with these credentials:
- **Username:** `demo` / **Password:** `demo123`
- **Username:** `trader1` / **Password:** `password1`
- **Username:** `trader2` / **Password:** `password2`

---

## For Your 10 Users

### Option A: Use the Helper Script (Recommended)

Generate hashes easily:

```bash
python3 generate_password_hashes.py
```

Then:
1. Select option **2** (Generate hashes for multiple users)
2. Enter each username and password
3. Copy the output table to your Auth tab

### Option B: Generate All at Once

Create a quick script:

```python
import bcrypt

users = [
    ("user1", "password1"),
    ("user2", "password2"),
    ("user3", "password3"),
    # ... add 10 users
]

for username, password in users:
    hashed = bcrypt.hashpw(password.encode('utf-8'), bcrypt.gensalt()).decode('utf-8')
    print(f"{username}\t{hashed}\temail@company.com\t{username.title()}")
```

---

## Your Auth Tab Should Look Like This

| username | password | email | name |
|----------|----------|-------|------|
| user1 | $2b$12$... | user1@company.com | User One |
| user2 | $2b$12$... | user2@company.com | User Two |
| user3 | $2b$12$... | user3@company.com | User Three |
| ... | ... | ... | ... |
| user10 | $2b$12$... | user10@company.com | User Ten |

---

## Key Features

✅ **Login Required** - Can't access dashboard without credentials
✅ **Bcrypt Hashing** - Passwords are securely hashed
✅ **1-Hour Cache** - User list cached to reduce API calls
✅ **User Display** - Name and email shown in sidebar
✅ **Easy Logout** - Logout button in sidebar
✅ **Session Based** - Login per browser session
✅ **Plain Text Fallback** - Still supports plain text passwords for testing

---

## Troubleshooting

**"Auth tab not found"**
→ Make sure sheet tab is named exactly **'Auth'** (case-sensitive)

**"Missing required column"**
→ Check columns: `username`, `password`, `email`, `name`

**"Invalid username or password"**
→ Verify the password hash is correct
→ Try a plain text password first to test

**Login page shows but no dashboard**
→ Your credentials aren't in the Auth tab yet
→ Add test users from above

---

## Managing 10 Users

### Add a New User
1. Open Auth tab in Google Sheet
2. Add a new row with: `username`, `hashed_password`, `email`, `name`
3. Generate hash using: `python3 generate_password_hashes.py`

### Update a Password
1. Generate new hash with: `python3 generate_password_hashes.py`
2. Replace the old hash in Auth tab
3. User can login next time with new password

### Remove a User
1. Delete the row from Auth tab
2. User will get "Invalid username or password" on next login

---

## Security Checklist

✅ Passwords hashed with bcrypt (not plain text)
✅ Google Sheets shared only with trusted team
✅ Service account JSON not in git repo
✅ User list cached (1 hour TTL)
✅ Session authentication per browser
✅ No sensitive data in logs

---

## Next Steps

1. ✅ Add 'Auth' tab to your Google Sheet
2. ✅ Add test users from above
3. ✅ Run `streamlit run dashboard.py`
4. ✅ Test login with demo/demo123
5. ✅ Replace test users with your 10 real users
6. ✅ Deploy to Streamlit Cloud

---

## Still Need Help?

See **AUTH_SETUP.md** for detailed instructions
