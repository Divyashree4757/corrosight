"""Local-development authentication for CorroSight.

What it is
----------
* Accounts live in a JSON user store (default `instance/users.json`, override with CORROSIGHT_USER_DB). The file holds
  only: user id, username, display name, email, role, admin flag, status, timestamps, a salted password HASH,
  failed-attempt counter and lock time. Plaintext passwords are never written anywhere.
* Passwords are hashed with PBKDF2-HMAC-SHA256 (Python standard library), a 16-byte random salt per password and
  390,000 iterations by default (CORROSIGHT_PBKDF2_ITERATIONS can lower it for tests). Hashes are compared in
  constant time (hmac.compare_digest).
* No usernames or passwords are hard-coded. The first accounts are created from the command line
  (see `python -m src.auth --help`); there is no public self-registration.
* Five consecutive failed sign-ins lock an account for 15 minutes. Error messages never reveal whether the username
  exists.

Limitations (development solution - not production authentication)
-------------------------------------------------------------------
* The JSON store has no encryption at rest, no multi-factor authentication, no SSO and no central session revocation.
* Streamlit sessions live in server memory and end when the browser tab closes or the server restarts; there are no
  persistent login cookies.
* Run behind HTTPS (e.g. a reverse proxy) in any shared deployment. For production use an identity provider
  (Streamlit's st.login with OIDC, Azure AD / Entra ID, Okta, Auth0 or Keycloak) and a managed database.
"""

from __future__ import annotations

import argparse
import base64
import getpass
import hashlib
import hmac
import json
import os
import re
import secrets
import sys
import threading
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path

from .rbac import ROLES

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DB = ROOT / "instance" / "users.json"
MAX_FAILED = 5
LOCK_MINUTES = 15
_lock = threading.Lock()


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _ts(dt: datetime) -> str:
    return dt.strftime("%Y-%m-%d %H:%M:%S UTC")


def _iterations() -> int:
    try:
        return max(1000, int(os.environ.get("CORROSIGHT_PBKDF2_ITERATIONS", "390000")))
    except ValueError:
        return 390000


# ---------------------------------------------------------------- password hashing
def hash_password(password: str, iterations: int | None = None) -> str:
    it = iterations or _iterations()
    salt = secrets.token_bytes(16)
    dk = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, it)
    return f"pbkdf2_sha256${it}${base64.b64encode(salt).decode()}${base64.b64encode(dk).decode()}"


def verify_password(password: str, stored: str) -> bool:
    try:
        algo, it, salt_b64, dk_b64 = stored.split("$")
        if algo != "pbkdf2_sha256":
            return False
        dk = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), base64.b64decode(salt_b64), int(it))
        return hmac.compare_digest(dk, base64.b64decode(dk_b64))
    except (ValueError, TypeError):
        return False


_DUMMY_HASH = None


def _dummy_verify(password: str):
    """Spend comparable time for unknown usernames so timing does not reveal which accounts exist."""
    global _DUMMY_HASH
    if _DUMMY_HASH is None:
        _DUMMY_HASH = hash_password("dummy-password-for-timing")
    verify_password(password, _DUMMY_HASH)


def password_problems(password: str) -> list[str]:
    p = []
    if len(password) < 10:
        p.append("at least 10 characters")
    if not re.search(r"[A-Za-z]", password):
        p.append("at least one letter")
    if not re.search(r"\d", password):
        p.append("at least one digit")
    return p


def generate_password() -> str:
    """Random temporary password that satisfies the policy (shown once, never stored in plaintext)."""
    while True:
        pw = secrets.token_urlsafe(12)
        if not password_problems(pw):
            return pw


# ---------------------------------------------------------------- user store
PUBLIC_FIELDS = ("user_id", "username", "display_name", "email", "role", "is_admin", "status", "created_utc",
                 "last_login_utc", "must_change_password")


@dataclass
class LoginResult:
    ok: bool
    user: dict | None = None
    message: str = ""


class UserStore:
    def __init__(self, path: str | Path | None = None):
        self.path = Path(path or os.environ.get("CORROSIGHT_USER_DB") or DEFAULT_DB)

    # -- persistence
    def _load(self) -> list[dict]:
        if not self.path.exists():
            return []
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
            return data.get("users", []) if isinstance(data, dict) else []
        except (json.JSONDecodeError, OSError):
            return []

    def _save(self, users: list[dict]):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.path.with_suffix(".tmp")
        tmp.write_text(json.dumps({"schema": 1, "users": users}, indent=1), encoding="utf-8")
        try:
            os.chmod(tmp, 0o600)
        except OSError:
            pass
        tmp.replace(self.path)

    @staticmethod
    def public(u: dict | None) -> dict | None:
        return None if u is None else {k: u.get(k) for k in PUBLIC_FIELDS}

    # -- queries
    def list_users(self) -> list[dict]:
        return [self.public(u) for u in self._load()]

    def get(self, user_id: str) -> dict | None:
        return self.public(next((u for u in self._load() if u["user_id"] == user_id), None))

    def find(self, username: str) -> dict | None:
        key = username.strip().lower()
        return self.public(next((u for u in self._load() if u["username"] == key), None))

    def is_empty(self) -> bool:
        return not self._load()

    # -- mutations
    def create_user(self, username: str, display_name: str, role: str, password: str, email: str = "",
                    is_admin: bool = False, must_change_password: bool = False) -> dict:
        username = username.strip().lower()
        if not re.fullmatch(r"[a-z0-9._@-]{3,64}", username):
            raise ValueError("Username must be 3-64 characters: letters, digits, '.', '_', '-', '@'.")
        if role not in ROLES:
            raise ValueError(f"Unknown role '{role}'. Choose one of: {', '.join(ROLES)}.")
        probs = password_problems(password)
        if probs:
            raise ValueError("Password needs " + ", ".join(probs) + ".")
        with _lock:
            users = self._load()
            if any(u["username"] == username for u in users):
                raise ValueError("That username already exists.")
            u = dict(user_id=f"U-{uuid.uuid4().hex[:10]}", username=username, display_name=display_name.strip() or username,
                     email=email.strip(), role=role, is_admin=bool(is_admin), status="active", created_utc=_ts(utc_now()),
                     last_login_utc=None, must_change_password=bool(must_change_password),
                     password_hash=hash_password(password), failed_attempts=0, locked_until=None)
            users.append(u)
            self._save(users)
        return self.public(u)

    def seed_from_records(self, records: list[dict]) -> int:
        """Create accounts from pre-hashed records (e.g. Streamlit Cloud secrets) when the store is EMPTY.

        Each record: username, role, password_hash (pbkdf2_sha256$...), optional display_name, email, is_admin.
        Plain passwords are never accepted here. Returns the number of accounts created (0 if the store already has users).
        """
        with _lock:
            if self._load():
                return 0
            users = []
            for r in records:
                username = str(r.get("username", "")).strip().lower()
                role, h = r.get("role"), str(r.get("password_hash", ""))
                if not re.fullmatch(r"[a-z0-9._@-]{3,64}", username) or role not in ROLES or not h.startswith("pbkdf2_sha256$"):
                    raise ValueError(f"Invalid seeded account record for '{username or '?'}'.")
                users.append(dict(user_id=f"U-{uuid.uuid4().hex[:10]}", username=username,
                                  display_name=str(r.get("display_name") or username).strip(), email=str(r.get("email", "")).strip(),
                                  role=role, is_admin=bool(r.get("is_admin", False)), status="active", created_utc=_ts(utc_now()),
                                  last_login_utc=None, must_change_password=False, password_hash=h, failed_attempts=0,
                                  locked_until=None))
            self._save(users)
            return len(users)

    def update_user(self, user_id: str, **changes) -> dict:
        allowed = {"display_name", "email", "role", "status", "is_admin"}
        bad = set(changes) - allowed
        if bad:
            raise ValueError(f"Cannot change: {', '.join(sorted(bad))}")
        if "role" in changes and changes["role"] not in ROLES:
            raise ValueError("Unknown role.")
        if "status" in changes and changes["status"] not in ("active", "inactive"):
            raise ValueError("Status must be 'active' or 'inactive'.")
        with _lock:
            users = self._load()
            u = next((x for x in users if x["user_id"] == user_id), None)
            if u is None:
                raise ValueError("User not found.")
            u.update(changes)
            if changes.get("status") == "active":
                u["failed_attempts"], u["locked_until"] = 0, None
            self._save(users)
        return self.public(u)

    def set_password(self, user_id: str, new_password: str, must_change: bool = False) -> None:
        probs = password_problems(new_password)
        if probs:
            raise ValueError("Password needs " + ", ".join(probs) + ".")
        with _lock:
            users = self._load()
            u = next((x for x in users if x["user_id"] == user_id), None)
            if u is None:
                raise ValueError("User not found.")
            u["password_hash"] = hash_password(new_password)
            u["must_change_password"] = bool(must_change)
            u["failed_attempts"], u["locked_until"] = 0, None
            self._save(users)

    def change_own_password(self, user_id: str, current: str, new_password: str) -> None:
        users = self._load()
        u = next((x for x in users if x["user_id"] == user_id), None)
        if u is None or not verify_password(current, u["password_hash"]):
            raise ValueError("Current password is incorrect.")
        if current == new_password:
            raise ValueError("Choose a password different from the current one.")
        self.set_password(user_id, new_password, must_change=False)

    def reset_password(self, user_id: str) -> str:
        """Admin reset: returns a one-time temporary password (to hand over securely); user must change it."""
        temp = generate_password()
        self.set_password(user_id, temp, must_change=True)
        return temp

    def authenticate(self, username: str, password: str) -> LoginResult:
        generic = "Invalid username or password."
        if not username.strip() or not password:
            return LoginResult(False, None, "Enter your username and password.")
        key = username.strip().lower()
        with _lock:
            users = self._load()
            u = next((x for x in users if x["username"] == key), None)
            if u is None:
                _dummy_verify(password)
                return LoginResult(False, None, generic)
            now = utc_now()
            if u.get("locked_until"):
                until = datetime.strptime(u["locked_until"], "%Y-%m-%d %H:%M:%S UTC").replace(tzinfo=timezone.utc)
                if until > now:
                    _dummy_verify(password)
                    mins = max(1, int((until - now).total_seconds() // 60) + 1)
                    return LoginResult(False, None, f"Too many failed attempts. Try again in about {mins} minute(s) "
                                                    "or ask an administrator.")
                u["locked_until"], u["failed_attempts"] = None, 0
            if not verify_password(password, u["password_hash"]):
                u["failed_attempts"] = int(u.get("failed_attempts") or 0) + 1
                if u["failed_attempts"] >= MAX_FAILED:
                    u["locked_until"] = _ts(now + timedelta(minutes=LOCK_MINUTES))
                self._save(users)
                return LoginResult(False, None, generic)
            if u.get("status") != "active":
                return LoginResult(False, None, "This account is inactive. Contact your administrator.")
            u["failed_attempts"], u["locked_until"], u["last_login_utc"] = 0, None, _ts(now)
            self._save(users)
            return LoginResult(True, self.public(u), "")


# ---------------------------------------------------------------- command line (first accounts, administration)
def _ask_password(prompt="Password: ") -> str:
    while True:
        p1 = getpass.getpass(prompt)
        probs = password_problems(p1)
        if probs:
            print("Password needs " + ", ".join(probs) + ".")
            continue
        if getpass.getpass("Repeat password: ") != p1:
            print("Passwords do not match.")
            continue
        return p1


def main(argv=None):
    ap = argparse.ArgumentParser(prog="python -m src.auth", description="Manage CorroSight user accounts (local store).")
    ap.add_argument("--db", help="user store path (default instance/users.json or $CORROSIGHT_USER_DB)")
    sub = ap.add_subparsers(dest="cmd", required=True)
    a = sub.add_parser("add", help="create an account (prompts for the password)")
    a.add_argument("username")
    a.add_argument("--name", default="")
    a.add_argument("--email", default="")
    a.add_argument("--role", required=True, choices=list(ROLES))
    a.add_argument("--admin", action="store_true", help="grant the separate user-administration capability")
    sub.add_parser("list", help="list accounts (no secrets)")
    r = sub.add_parser("set-role")
    r.add_argument("username")
    r.add_argument("role", choices=list(ROLES))
    for cmd in ("activate", "deactivate", "reset-password"):
        sub.add_parser(cmd).add_argument("username")
    d = sub.add_parser("demo", help="create one demo account per role (+ an admin) with RANDOM passwords printed once")
    d.add_argument("--force", action="store_true", help="allow when the store already has accounts")
    args = ap.parse_args(argv)
    store = UserStore(args.db)

    def need(username):
        u = store.find(username)
        if u is None:
            sys.exit(f"No such user: {username}")
        return u

    if args.cmd == "add":
        pw = _ask_password()
        u = store.create_user(args.username, args.name, args.role, pw, args.email, args.admin)
        print(f"Created {u['username']} ({ROLES[u['role']]['title']}{', admin' if u['is_admin'] else ''}) in {store.path}")
    elif args.cmd == "list":
        for u in store.list_users():
            print(f"{u['username']:<22} {ROLES[u['role']]['title']:<45} {'admin ' if u['is_admin'] else ''}{u['status']:<9} "
                  f"last login: {u['last_login_utc'] or '-'}")
    elif args.cmd == "set-role":
        store.update_user(need(args.username)["user_id"], role=args.role)
        print("Role updated.")
    elif args.cmd in ("activate", "deactivate"):
        store.update_user(need(args.username)["user_id"], status="active" if args.cmd == "activate" else "inactive")
        print(f"Account {args.cmd}d.")
    elif args.cmd == "reset-password":
        temp = store.reset_password(need(args.username)["user_id"])
        print(f"Temporary password (shown once; user must change it at next sign-in): {temp}")
    elif args.cmd == "demo":
        if not store.is_empty() and not args.force:
            sys.exit("The user store already has accounts. Use --force to add demo accounts anyway.")
        rows = [("engineer", "Demo Integrity Engineer", "engineer", False), ("analyst", "Demo Data Analyst", "analyst", False),
                ("planner", "Demo Planner", "planner", False), ("manager", "Demo Asset Integrity Manager", "manager", False),
                ("admin", "Demo Administrator", "manager", True)]
        print(f"Demo accounts created in {store.path} (passwords are random and shown only now):\n")
        for username, name, role, admin in rows:
            if store.find(username):
                print(f"  {username:<10} already exists - skipped")
                continue
            pw = generate_password()
            store.create_user(username, name, role, pw, is_admin=admin)
            print(f"  {username:<10} {pw:<20} {ROLES[role]['title']}{'  [+ user administration]' if admin else ''}")
        print("\nStore these passwords securely. Use 'reset-password' if one is lost.")


if __name__ == "__main__":
    main()
