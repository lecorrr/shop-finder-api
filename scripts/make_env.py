"""Create .env from .env.example with a fresh secret key and database password.

python3 scripts/make_env.py            # refuses to replace an existing .env
python3 scripts/make_env.py --force
"""

import argparse
import secrets
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PLACEHOLDER = "change-me"


def build_env(template: str) -> str:
    secret_key = secrets.token_urlsafe(50)
    # URL-safe, because the password also goes inside DATABASE_URL.
    db_password = secrets.token_urlsafe(24)
    lines = []
    for line in template.splitlines():
        if line.startswith("DJANGO_SECRET_KEY="):
            line = f"DJANGO_SECRET_KEY={secret_key}"
        lines.append(line.replace(PLACEHOLDER, db_password))
    return "\n".join(lines) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--force", action="store_true", help="replace an existing .env")
    args = parser.parse_args()

    target = ROOT / ".env"
    if target.exists() and not args.force:
        print(f"{target} already exists; use --force to replace it", file=sys.stderr)
        return 1
    content = build_env((ROOT / ".env.example").read_text())
    if PLACEHOLDER in content:
        print("a placeholder was left in .env; check .env.example", file=sys.stderr)
        return 1
    target.write_text(content)
    target.chmod(0o600)
    print(f"wrote {target}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
