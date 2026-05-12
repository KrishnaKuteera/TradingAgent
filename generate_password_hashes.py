#!/usr/bin/env python3
"""
Password Hash Generator for Stock Buy Zone Analyzer

Usage:
    python3 generate_password_hashes.py

Creates bcrypt hashes for user passwords.
"""

import bcrypt

def hash_password(password):
    """Generate bcrypt hash for a password"""
    salt = bcrypt.gensalt()
    hashed = bcrypt.hashpw(password.encode('utf-8'), salt)
    return hashed.decode('utf-8')

def verify_password(password, hashed):
    """Verify a password against its hash"""
    return bcrypt.checkpw(password.encode('utf-8'), hashed.encode('utf-8'))

def main():
    print("\n" + "="*60)
    print("Stock Buy Zone Analyzer - Password Hash Generator")
    print("="*60 + "\n")

    print("Choose an option:")
    print("1. Generate single hash")
    print("2. Generate hashes for multiple users")
    print("3. Test password verification")
    print("4. Generate test users (10 users)")

    choice = input("\nSelect option (1-4): ").strip()

    if choice == "1":
        password = input("Enter password to hash: ")
        hashed = hash_password(password)
        print(f"\n✅ Hash: {hashed}")
        print("\nCopy this hash to your Google Sheet 'Auth' tab")

    elif choice == "2":
        print("\nEnter users (format: username:password)")
        print("Example: john_doe:secure_password_123")
        print("Type 'done' when finished\n")

        users = []
        while True:
            user_input = input("User (username:password): ").strip()
            if user_input.lower() == 'done':
                break
            if ':' not in user_input:
                print("❌ Invalid format. Use username:password")
                continue
            username, password = user_input.split(':', 1)
            users.append((username, password))

        print("\n" + "="*60)
        print("Copy this table to your Google Sheet 'Auth' tab:")
        print("="*60)
        print("username\tpassword\temail\tname")

        for username, password in users:
            hashed = hash_password(password)
            email = input(f"Email for {username}: ").strip()
            name = input(f"Full name for {username}: ").strip()
            print(f"{username}\t{hashed}\t{email}\t{name}")

    elif choice == "3":
        hashed = input("Enter password hash: ").strip()
        password = input("Enter password to test: ")

        if verify_password(password, hashed):
            print("\n✅ Password matches!")
        else:
            print("\n❌ Password does NOT match")

    elif choice == "4":
        print("\nGenerating 10 test users...\n")
        print("="*80)
        print("Copy this table to your Google Sheet 'Auth' tab:")
        print("="*80)
        print("username\tpassword\temail\tname")

        for i in range(1, 11):
            username = f"trader{i}"
            password = f"password{i}"
            email = f"trader{i}@company.com"
            name = f"Trader {i}"
            hashed = hash_password(password)
            print(f"{username}\t{hashed}\t{email}\t{name}")

        print("\n" + "="*80)
        print("Test Users (for reference, not to be stored anywhere):")
        print("="*80)
        for i in range(1, 11):
            print(f"trader{i} / password{i}")

    else:
        print("❌ Invalid option")

    print("\n" + "="*60 + "\n")

if __name__ == "__main__":
    main()
