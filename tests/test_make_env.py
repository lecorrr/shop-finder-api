import argparse
import importlib.util
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
_spec = importlib.util.spec_from_file_location("make_env", ROOT / "scripts" / "make_env.py")
make_env = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(make_env)

TEMPLATE = (ROOT / ".env.example").read_text()


def values(content: str) -> dict[str, str]:
    pairs = (line.split("=", 1) for line in content.splitlines() if "=" in line)
    return {key: value for key, value in pairs if not key.startswith("#")}


def test_development_env_gets_fresh_secrets():
    first, second = values(make_env.build_env(TEMPLATE)), values(make_env.build_env(TEMPLATE))

    assert make_env.PLACEHOLDER not in "".join(first.values())
    assert first["DJANGO_SECRET_KEY"] != second["DJANGO_SECRET_KEY"]
    assert first["POSTGRES_PASSWORD"] in first["DATABASE_URL"]
    assert first["DJANGO_DEBUG"] == "true"


def test_server_env():
    env = values(make_env.build_env(TEMPLATE, "api.example.com"))

    assert env["DJANGO_DEBUG"] == "false"
    assert env["DJANGO_ALLOWED_HOSTS"].split(",") == ["api.example.com", "127.0.0.1", "localhost"]
    assert env["DJANGO_CSRF_TRUSTED_ORIGINS"] == "https://api.example.com"
    assert env["DJANGO_SECURE_COOKIES"] == "true"
    assert env["GUNICORN_CMD_ARGS"] == "--threads=4"
    assert env["POSTGRES_PASSWORD"] in env["DATABASE_URL"]


def test_values_have_no_spaces_so_shells_and_compose_read_them_alike():
    env = values(make_env.build_env(TEMPLATE, "api.example.com"))

    assert [key for key, value in env.items() if " " in value] == []


@pytest.mark.parametrize(
    "host", ["shop.example.com", "Shop.Example.COM", "shop.3-120-1-2.sslip.io"]
)
def test_valid_host_names(host):
    assert make_env.host_name(host) == host.lower()


@pytest.mark.parametrize(
    "host",
    [
        "",
        "localhost",
        "https://shop.example.com",
        "shop.example.com/api",
        "a b.com",
        "-x.example.com",
    ],
)
def test_invalid_host_names(host):
    with pytest.raises(argparse.ArgumentTypeError):
        make_env.host_name(host)
