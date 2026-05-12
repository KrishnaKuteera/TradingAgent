#!/usr/bin/env python3
"""
Test password hashing and verification
"""

import bcrypt

def hash_password(password):
    """Generate bcrypt hash for a password"""
    salt = bcrypt.gensalt()
    hashed = bcrypt.hashpw(password.encode('utf-8'), salt)
    return hashed.decode('utf-8')

def verify_password(stored_hash, provided_password):
    """Verify a password against its hash"""
    try:
        return bcrypt.checkpw(provided_password.encode('utf-8'), stored_hash.encode('utf-8'))
    except Exception as e:
        print(f"❌ Verification error: {e}")
        return False

print("="*60)
print("Password Hash Verification Test")
print("="*60 + "\n")

# Get input
password = input("Enter the password you want to test: ").strip()
hash_value = input("Enter the hash (paste from Google Sheet): ").strip()

print("\n" + "-"*60)
print("Testing...")
print("-"*60)

# Verify
if verify_password(hash_value, password):
    print("✅ SUCCESS! Password matches the hash")
    print("\nThis means:")
    print("- Hash is correctly formatted")
    print("- Password is correct")
    print("- Login should work!")
else:
    print("❌ FAILED! Password does NOT match the hash")
    print("\nPossible issues:")
    print("1. Wrong password")
    print("2. Hash is corrupted or has extra spaces")
    print("3. Hash was copied incorrectly")

print("\n" + "="*60)
print("Debug Info:")
print("="*60)
print(f"Password: {password}")
print(f"Password length: {len(password)}")
print(f"Hash: {hash_value}")
print(f"Hash length: {len(hash_value)}")
print(f"Hash starts with: {hash_value[:20]}")

print("\n" + "="*60)
print("Generate a NEW hash for this password:")
print("="*60)
new_hash = hash_password(password)
print(f"\nNEW HASH:\n{new_hash}")
print("\nCopy this to your Google Sheet and try again!")
print("="*60)
