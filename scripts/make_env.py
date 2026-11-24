"""Create .env from .env.example with a fresh secret key and database password.

    python3 scripts/make_env.py                          # for development on this machine
    python3 scripts/make_env.py --host api.example.com   # for a server behind an HTTPS proxy
    python3 scripts/make_env.py --force                  # replace an existing .env

Do not replace the .env of a server whose database already exists: PostgreSQL keeps the
password it was created with, and a new one in .env would lock the API out.
"""

import argparse
import re
import secrets
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PLACEHOLDER = "change-me"
HOST_NAME = re.compile(r"^(?=.{4,253}$)([a-z0-9]([a-z0-9-]{0,61}[a-z0-9])?\.)+[a-z]{2,63}$")


def host_name(value: str) -> str:
    """argparse type: a lowercase DNS name such as api.example.com, nothing else."""
    host = value.strip().lower()
    if not HOST_NAME.match(host):
        raise argparse.ArgumentTypeError(f"{value!r} is not a host name like api.example.com")
    return host


def server_settings(host: str) -> dict[str, str]:
    """What changes when the API runs on a server behind an HTTPS proxy."""
    return {
        "DJANGO_DEBUG": "false",
        # The container health check calls 127.0.0.1, so it must stay allowed.
        "DJANGO_ALLOWED_HOSTS": f"{host},127.0.0.1,localhost",
        "DJANGO_CSRF_TRUSTED_ORIGINS": f"https://{host}",
        "DJANGO_SECURE_COOKIES": "true",
        # One process with threads fits a small server better than several processes.
        "WEB_CONCURRENCY": "1",
        "GUNICORN_CMD_ARGS": "--threads=4",
    }


def build_env(template: str, host: str | None = None) -> str:
    secret_key = secrets.token_urlsafe(50)
    # URL-safe, because the password also goes inside DATABASE_URL.
    db_password = secrets.token_urlsafe(24)
    overrides = server_settings(host) if host else {}
    lines = []
    for line in template.splitlines():
        key = line.split("=", 1)[0] if "=" in line and not line.startswith("#") else ""
        if key == "DJANGO_SECRET_KEY":
            line = f"DJANGO_SECRET_KEY={secret_key}"
        elif key in overrides:
            line = f"{key}={overrides.pop(key)}"
        lines.append(line.replace(PLACEHOLDER, db_password))
    if overrides:
        lines += ["", "# Server settings"] + [f"{key}={value}" for key, value in overrides.items()]
    return "\n".join(lines) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--host", type=host_name, help="public host name of a server")
    parser.add_argument("--force", action="store_true", help="replace an existing .env")
    args = parser.parse_args()

    target = ROOT / ".env"
    if target.exists() and not args.force:
        print(f"{target} already exists; use --force to replace it", file=sys.stderr)
        return 1
    content = build_env((ROOT / ".env.example").read_text(), args.host)
    if PLACEHOLDER in content:
        print("a placeholder was left in .env; check .env.example", file=sys.stderr)
        return 1
    target.write_text(content)
    target.chmod(0o600)
    print(f"wrote {target}" + (f" for {args.host}" if args.host else ""))
    return 0


if __name__ == "__main__":
    sys.exit(main())
