"""Rules about which code may use what, checked here so they do not erode."""

import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
APPS = ["accounts", "shops", "catalog", "offers", "imports", "stats", "core", "shopfinder"]
FRAMEWORKS = {"django", "rest_framework", "pymongo", "bson", "httpx", "celery"}


def source_files() -> list[Path]:
    return [
        path
        for app in APPS
        for path in (ROOT / app).rglob("*.py")
        if "migrations" not in path.parts
    ]


def imported_modules(path: Path) -> set[str]:
    modules = set()
    for node in ast.walk(ast.parse(path.read_text())):
        if isinstance(node, ast.Import):
            modules |= {alias.name for alias in node.names}
        elif isinstance(node, ast.ImportFrom) and node.module:
            modules.add(node.module)
    return modules


def test_only_one_module_creates_the_mongodb_client():
    creators = [
        path.relative_to(ROOT).as_posix()
        for path in source_files()
        if "MongoClient(" in path.read_text()
    ]
    assert creators == ["shopfinder/mongo.py"]


def test_views_reach_mongodb_only_through_repositories():
    for path in ROOT.glob("*/views.py"):
        roots = {name.split(".")[0] for name in imported_modules(path)}
        assert not roots & {"pymongo", "bson"}, path.name


def test_parsers_have_no_framework_dependencies():
    for name in ["imports/feeds.py", "catalog/barcodes.py"]:
        roots = {module.split(".")[0] for module in imported_modules(ROOT / name)}
        assert not roots & FRAMEWORKS, name


def test_every_app_is_installed():
    from django.conf import settings

    assert set(APPS) - {"shopfinder"} <= set(settings.INSTALLED_APPS)
