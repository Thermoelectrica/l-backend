#!/usr/bin/env python3
"""CLI utility to generate INSERT statements for inspectors"""

import sys
from pathlib import Path
from getpass import getpass

# Add parent directory to path so we can import app modules
sys.path.insert(0, str(Path(__file__).parent.parent))

from app.models.inspector import AccessLevel
from app.services.auth import AuthService


def add_inspector(full_name: str, username: str, password: str, access_level: str, is_internal: bool):
    """Generate INSERT statement for a new inspector

    access_level and is_internal are spelled out rather than left to the column defaults:
    an omitted access_level silently yields READ, and an omitted is_internal silently yields
    an external user (or, if the polarity is ever misread, one that sees every new plant).
    """
    auth_service = AuthService()

    # Hash the password
    password_hash = auth_service.hash_password(password)

    # Generate INSERT statement
    insert_statement = f"""INSERT INTO lesiv.inspector
    (full_name, username, password_hash, access_level, is_internal)
VALUES ('{full_name}', '{username}', '{password_hash}', '{access_level}', {str(is_internal).upper()});"""

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

    levels = [level.value for level in AccessLevel]
    access_level = input(f"Access level {levels} [MODIFY]: ").strip().upper() or "MODIFY"
    if access_level not in levels:
        print(f"❌ Error: Access level must be one of {levels}", file=sys.stderr)
        sys.exit(1)

    # Internal inspectors are auto-granted access to every plant created from now on;
    # external users only ever see plants granted to them explicitly.
    internal_answer = input("Internal (company) inspector? [y/N]: ").strip().lower()
    is_internal = internal_answer in ("y", "yes")

    # Generate INSERT statement
    add_inspector(full_name, username, password, access_level, is_internal)


if __name__ == "__main__":
    main()
