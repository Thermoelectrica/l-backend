#!/usr/bin/env python3
"""CLI utility to generate INSERT statements for inspectors"""

import sys
from pathlib import Path
from getpass import getpass

# Add parent directory to path so we can import app modules
sys.path.insert(0, str(Path(__file__).parent.parent))

from app.services.auth import AuthService


def add_inspector(full_name: str, username: str, password: str):
    """Generate INSERT statement for a new inspector"""
    auth_service = AuthService()

    # Hash the password
    password_hash = auth_service.hash_password(password)

    # Generate INSERT statement
    insert_statement = f"""INSERT INTO lesiv.inspector (full_name, username, password_hash)
VALUES ('{full_name}', '{username}', '{password_hash}');"""

    print(insert_statement)


def main():
    """Main CLI entry point"""
    print("=== Generate Inspector INSERT Statement ===\n")

    # Get inspector details
    full_name = input("Full Name: ").strip()
    if not full_name:
        print("❌ Error: Full name is required", file=sys.stderr)
        sys.exit(1)

    username = input("Username: ").strip()
    if not username:
        print("❌ Error: Username is required", file=sys.stderr)
        sys.exit(1)

    # Get password securely
    password = getpass("Password: ")
    if not password:
        print("❌ Error: Password is required", file=sys.stderr)
        sys.exit(1)

    password_confirm = getpass("Confirm Password: ")
    if password != password_confirm:
        print("❌ Error: Passwords do not match", file=sys.stderr)
        sys.exit(1)

    # Generate INSERT statement
    add_inspector(full_name, username, password)


if __name__ == "__main__":
    main()
