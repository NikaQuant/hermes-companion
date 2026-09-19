from __future__ import annotations

import argparse
import getpass
import sys
from pathlib import Path


def main() -> None:
    parser = argparse.ArgumentParser(description="Reset a Hermes Companion administrator password")
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--email")
    args = parser.parse_args()
    root = args.root.resolve()
    sys.path.insert(0, str(root / "services" / "bridge"))
    from app.config import Settings
    from app.db import Database
    from app.security import hash_password, utc_timestamp

    settings = Settings.from_env(project_root=root, env_file=root / ".env")
    database = Database(settings.database_path)
    email = (args.email or input("Administrator email: ")).strip().lower()
    password = getpass.getpass("New password (12+ characters): ")
    confirm = getpass.getpass("Confirm new password: ")
    if password != confirm:
        raise SystemExit("Passwords do not match")
    encoded = hash_password(password)
    with database.connect() as connection:
        row = connection.execute("SELECT id FROM users WHERE email=?", (email,)).fetchone()
        if not row:
            raise SystemExit("No Companion user exists with that email")
        connection.execute("UPDATE users SET password_hash=? WHERE id=?", (encoded, row["id"]))
        connection.execute(
            "UPDATE auth_tokens SET revoked_at=? WHERE user_id=? AND revoked_at IS NULL",
            (utc_timestamp(), row["id"]),
        )
    database.audit(event="auth.password_reset_local", user_id=row["id"], metadata={"email": email})
    print("Password reset. All existing device sessions were revoked.")


if __name__ == "__main__":
    main()
