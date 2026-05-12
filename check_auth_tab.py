#!/usr/bin/env python3
"""
Check Auth tab in Google Sheet for issues
"""

import gspread
from google.oauth2.service_account import Credentials
import os

print("="*60)
print("Auth Tab Diagnostic")
print("="*60 + "\n")

# Connect to Google Sheets
try:
    SCOPES = ['https://www.googleapis.com/auth/spreadsheets', 'https://www.googleapis.com/auth/drive']
    json_file = 'tradeportfolioagent-52f42fe31773.json'

    if not os.path.exists(json_file):
        print(f"❌ Service account file not found: {json_file}")
        exit(1)

    credentials = Credentials.from_service_account_file(json_file, scopes=SCOPES)
    client = gspread.authorize(credentials)

    print("✅ Connected to Google Sheets\n")

    # Open sheet
    spreadsheet = client.open('Copy of StockTracker')
    print(f"✅ Opened spreadsheet: 'Copy of StockTracker'\n")

    # Get Auth sheet
    try:
        auth_sheet = spreadsheet.worksheet('Auth')
        print("✅ Found 'Auth' tab\n")
    except:
        print("❌ 'Auth' tab not found!")
        print("Available sheets:", [ws.title for ws in spreadsheet.worksheets()])
        exit(1)

    # Get data
    all_values = auth_sheet.get_all_values()

    print(f"Total rows: {len(all_values)}")
    print(f"Total columns: {len(all_values[0]) if all_values else 0}\n")

    if len(all_values) < 2:
        print("❌ Auth tab is empty or only has headers!")
        exit(1)

    # Check headers
    headers = all_values[0]
    print("Headers (Row 1):")
    for i, h in enumerate(headers):
        print(f"  Column {i}: '{h}'")

    print("\n" + "-"*60)
    print("Users in Auth tab:")
    print("-"*60)

    header_lower = [h.lower().strip() for h in headers]

    for idx, row in enumerate(all_values[1:], start=2):
        if not row or not row[0].strip():
            continue

        print(f"\nRow {idx}:")
        for i, val in enumerate(row):
            col_name = headers[i] if i < len(headers) else f"Column {i}"
            if 'password' in col_name.lower():
                # Mask password hash for security
                display_val = val[:20] + "..." if len(val) > 20 else val
                print(f"  {col_name}: {display_val}")
            else:
                print(f"  {col_name}: {val}")

    print("\n" + "="*60)
    print("Validation Checks:")
    print("="*60)

    required_cols = ['username', 'password', 'email', 'name']
    for col in required_cols:
        if col in header_lower:
            print(f"✅ Column '{col}' found")
        else:
            print(f"❌ Column '{col}' MISSING (required)")

    # Check for common issues
    print("\n" + "="*60)
    print("Common Issues Check:")
    print("="*60)

    col_indices = {col: header_lower.index(col) for col in required_cols if col in header_lower}

    if 'username' in col_indices and 'password' in col_indices:
        user_count = 0
        for row in all_values[1:]:
            if len(row) > max(col_indices.values()) and row[0].strip():
                user_count += 1
                username = row[col_indices['username']].strip()
                password = row[col_indices['password']].strip()

                # Check password format
                if not password.startswith('$2b$12$'):
                    print(f"⚠️  User '{username}': Password is not bcrypt hash (doesn't start with $2b$12$)")
                    print(f"   Password length: {len(password)}")
                    if len(password) < 30:
                        print(f"   ℹ️  This looks like plain text (bcrypt hashes are 60 chars)")

        print(f"\nTotal users found: {user_count}")

except Exception as e:
    print(f"❌ Error: {str(e)}")
    import traceback
    traceback.print_exc()

print("\n" + "="*60)
