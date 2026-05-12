# Authentication Setup Guide

## 1. Create the 'Auth' Tab in Your Google Sheet

Go to your "Copy of StockTracker" Google Sheet and add a new tab named **'Auth'** (exactly).

### Required Columns (in this order):
- `username` - Unique username for each user
- `password` - Password (either plain text or bcrypt hash)
- `email` - User's email address
- `name` - User's full name

### Example Data:

| username | password | email | name |
|----------|----------|-------|------|
| john_doe | $2b$12$... | john@example.com | John Doe |
| jane_smith | $2b$12$... | jane@example.com | Jane Smith |
| alice_trader | $2b$12$... | alice@example.com | Alice Trader |

## 2. Generate Bcrypt Hashes for Passwords

**Security Best Practice**: Store passwords as bcrypt hashes, not plain text.

### Option A: Use Python (Recommended)

```python
import bcrypt

password = "your_password_here"
hashed = bcrypt.hashpw(password.encode('utf-8'), bcrypt.gensalt())
print(hashed.decode('utf-8'))
```

Example output: `$2b$12$R9h7cIPz0gi.URNNX3kh2OPST9/PgBkqquzi.Ss7KIUgO2t0jKMUm`

### Option B: Quick Hash Generator Script

Create `hash_passwords.py`:

```python
import bcrypt

users = [
    {"username": "john_doe", "password": "john_password_123"},
    {"username": "jane_smith", "password": "jane_password_456"},
    {"username": "alice_trader", "password": "alice_password_789"},
]

for user in users:
    hashed = bcrypt.hashpw(user['password'].encode('utf-8'), bcrypt.gensalt()).decode('utf-8')
    print(f"{user['username']}: {hashed}")
```

Run it:
```bash
python3 hash_passwords.py
```

## 3. Add Users to Auth Tab

1. Go to your Google Sheet
2. Open the **'Auth'** tab
3. Add each user with:
   - Username
   - Hashed password (from above)
   - Email
   - Name

Example:
```
| john_doe | $2b$12$R9h7cIPz0gi.URNNX3kh2OPST9/PgBkqquzi.Ss7KIUgO2t0jKMUm | john@company.com | John Doe |
| jane_smith | $2b$12$KL3m9Vq2zXpQrT4wYjK5uL6mN7oP8aSbCdEfGhIjKlMnOpQrStUvWxYz | jane@company.com | Jane Smith |
```

## 4. Test Authentication

1. Stop the dashboard (Ctrl+C)
2. Start it again:
   ```bash
   streamlit run dashboard.py
   ```
3. You should see the **Login** screen
4. Enter any username/password from your Auth tab
5. If successful, you'll see the trading dashboard

## Security Notes

✅ **Hashed passwords** - Use bcrypt hashes, not plain text
✅ **Google Sheets** - Only share with trusted team members
✅ **Service account** - Never commit to GitHub
✅ **1-hour cache** - User list is cached to reduce API calls
✅ **Session-based** - Authentication state per browser session

## Troubleshooting

**"Auth tab not found"**
- Ensure the sheet tab is named exactly **'Auth'** (case-sensitive)

**"Missing required column"**
- Check all columns exist: `username`, `password`, `email`, `name`
- Check spelling and capitalization

**"Invalid username or password"**
- Verify password hash is correct
- Ensure no extra spaces in cells
- Try a plain text password first for testing, then upgrade to hashes

**"No users found"**
- Ensure Auth tab has data starting from row 2 (row 1 = headers)

## Default Test Users (Plain Text)

For initial testing, you can use plain text passwords:

| username | password | email | name |
|----------|----------|-------|------|
| demo | demo123 | demo@example.com | Demo User |
| trader | password | trader@example.com | Trader One |

**After testing**, replace with bcrypt hashes for security.

## Manage 10 Users Easily

Create a spreadsheet with user info, generate hashes in bulk with the script above, then paste into the Auth tab.

**10-User Example:**
```python
users = [
    "user1", "user2", "user3", "user4", "user5",
    "user6", "user7", "user8", "user9", "user10"
]

for username in users:
    password = f"secure_pass_{username}"  # Change this
    hashed = bcrypt.hashpw(password.encode('utf-8'), bcrypt.gensalt()).decode('utf-8')
    print(f"{username}\t{hashed}\t{username}@company.com\t{username.replace('_', ' ').title()}")
```

## Features

✅ Login screen before dashboard
✅ User list cached for 1 hour (reduces API calls)
✅ Supports both plain text and bcrypt hashes
✅ Session-based authentication
✅ User info displayed in sidebar
✅ Logout button in sidebar
✅ Dashboard only renders after successful login
