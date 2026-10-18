"""Locate AstrBot conversation databases without hardcoded user paths.

Official layouts covered:

* AstrBot Desktop: ``~/.astrbot/data/data_v4.db``
* AstrBot Launcher: ``~/.astrbot_launcher/instances/<id>/core/data/data_v4.db``
  (or the custom data directory stored in the launcher's ``.data-dir.json``)
* AstrBot source / current directory: ``<root>/data/data_v4.db``
* AstrBot CLI: ``~/.local/share/astrbot/data/data_v4.db``

``data_v3.db`` is included as a legacy database.  Every candidate is opened
read-only and checked for the ``conversations`` schema before it is returned.
"""

from __future__ import annotations

import json
import os
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Mapping

from .db import DatabaseInfo, InvalidDatabaseError, validate_database

DB_FILENAMES = ("data_v4.db", "data_v3.db")
LAUNCHER_CONFIG_SUBDIR = "com.github.raven95676.astrbot-launcher"
LAUNCHER_DATA_OVERRIDE = ".data-dir.json"
APP_CONFIG_SUBDIR = "AstrBotConversationManager"
APP_CONFIG_FILE = "config.json"


@dataclass(frozen=True)
class DatabaseCandidate:
    path: Path
    kind: str
    root: Path | None = None
    instance: str | None = None
    mtime: float = 0.0
    legacy: bool = False

    @property
    def display_name(self) -> str:
        names = {
            "desktop": "AstrBot Desktop",
            "launcher": "AstrBot Launcher",
            "source": "AstrBot 源码目录",
            "cli": "AstrBot CLI",
            "custom": "自定义数据库",
        }
        name = names.get(self.kind, self.kind)
        if self.kind == "launcher" and self.instance:
            return f"{name} · {self.instance}"
        if self.legacy:
            return f"{name} (legacy data_v3)"
        return name


def _home(home: str | Path | None) -> Path:
    return Path(home).expanduser().resolve() if home is not None else Path.home()


def _appdata_dir(home: Path, appdata: str | Path | None) -> Path:
    if appdata is not None:
        return Path(appdata).expanduser().resolve()
    if os.name == "nt":
        return Path(os.environ.get("APPDATA", home / "AppData" / "Roaming"))
    if sys.platform == "darwin":
        return home / "Library" / "Application Support"
    return Path(os.environ.get("XDG_CONFIG_HOME", home / ".config"))


def _db_files(data_dir: Path) -> Iterable[Path]:
    for name in DB_FILENAMES:
        path = data_dir / name
        if path.is_file():
            yield path


def _launcher_candidates(data_dir: Path) -> Iterable[DatabaseCandidate]:
    instances_dir = data_dir / "instances"
    if not instances_dir.is_dir():
        return
    for instance_dir in sorted(instances_dir.iterdir(), key=lambda p: p.name.lower()):
        if not instance_dir.is_dir():
            continue
        data_path = instance_dir / "core" / "data"
        for db_path in _db_files(data_path):
            yield DatabaseCandidate(
                path=db_path,
                kind="launcher",
                root=data_dir,
                instance=instance_dir.name,
                mtime=db_path.stat().st_mtime,
                legacy=db_path.name.lower().startswith("data_v3"),
            )


def _launcher_override(appdata: Path) -> Path | None:
    override = (
        appdata / LAUNCHER_CONFIG_SUBDIR / LAUNCHER_DATA_OVERRIDE
    )
    try:
        payload = json.loads(override.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError, TypeError):
        return None

    data_dir = payload.get("data_dir") if isinstance(payload, dict) else None
    if not isinstance(data_dir, str) or not data_dir.strip():
        return None

    candidate = Path(data_dir).expanduser()
    if not candidate.is_absolute():
        return None
    return candidate.resolve()


def _validated(path: Path, kind: str, root: Path | None = None,
               instance: str | None = None) -> DatabaseCandidate | None:
    try:
        info: DatabaseInfo = validate_database(path)
    except (InvalidDatabaseError, OSError):
        return None
    return DatabaseCandidate(
        path=info.path,
        kind=kind,
        root=root,
        instance=instance,
        mtime=info.mtime,
        legacy=info.legacy,
    )


def detect_databases(
    home: str | Path | None = None,
    appdata: str | Path | None = None,
    cwd: str | Path | None = None,
    env: Mapping[str, str] | None = None,
    saved_path: str | Path | None = None,
    include_saved: bool = True,
) -> list[DatabaseCandidate]:
    """Return every valid AstrBot conversation database found.

    Detection is intentionally limited to the official layouts and the
    current directory; it never scans a whole drive.  A manual database
    selected in the UI can be stored separately with
    :func:`save_last_database`.
    """

    home_path = _home(home)
    appdata_path = _appdata_dir(home_path, appdata)
    cwd_path = Path(cwd).expanduser().resolve() if cwd is not None else Path.cwd()
    environment = dict(env if env is not None else os.environ)

    if include_saved and saved_path is None:
        saved_path = load_last_database(home=home_path, appdata=appdata_path)

    found: dict[Path, tuple[int, DatabaseCandidate]] = {}

    def add(priority: int, candidate: DatabaseCandidate | None) -> None:
        if candidate is None:
            return
        key = candidate.path.resolve()
        previous = found.get(key)
        if previous is None or priority < previous[0]:
            found[key] = (priority, candidate)

    # 1. Explicit environment variable.
    explicit = environment.get("ASTRBOT_CONVERSATION_DB")
    if explicit:
        add(0, _validated(Path(explicit), "custom"))

    # 2. Last database selected in the UI.
    if saved_path:
        add(1, _validated(Path(saved_path), "custom"))

    # 3. ASTRBOT_ROOT, used by source installations.
    astrbot_root = environment.get("ASTRBOT_ROOT")
    if astrbot_root:
        root = Path(astrbot_root).expanduser().resolve()
        for db_path in _db_files(root / "data"):
            add(2, _validated(db_path, "source", root=root))

    # 4. AstrBot Desktop.
    desktop_root = home_path / ".astrbot"
    for db_path in _db_files(desktop_root / "data"):
        add(3, _validated(db_path, "desktop", root=desktop_root))

    # 5. AstrBot Launcher, default data directory.
    launcher_root = home_path / ".astrbot_launcher"
    for candidate in _launcher_candidates(launcher_root):
        add(4, candidate)

    # 6. AstrBot Launcher with a custom data directory.
    custom_launcher_root = _launcher_override(appdata_path)
    if custom_launcher_root is not None:
        for candidate in _launcher_candidates(custom_launcher_root):
            add(4, candidate)

    # 7. AstrBot CLI / uv installation.
    cli_root = home_path / ".local" / "share" / "astrbot"
    for db_path in _db_files(cli_root / "data"):
        add(5, _validated(db_path, "cli", root=cli_root))

    # 8. Current directory and a few parent directories (source checkout).
    #    A source install keeps the database at <root>/data/data_v4.db; the
    #    ASTRBOT_ROOT environment variable is the explicit way to point at a
    #    checkout that is not the current directory.
    for root in (cwd_path, *list(cwd_path.parents)[:3]):
        for db_path in _db_files(root / "data"):
            add(6, _validated(db_path, "source", root=root))
        for db_path in _db_files(root):
            add(6, _validated(db_path, "source", root=root))

    ordered = sorted(
        found.values(),
        key=lambda pair: (pair[0], -pair[1].mtime, str(pair[1].path).lower()),
    )
    return [candidate for _, candidate in ordered]


def _app_config_path(home: Path, appdata: Path) -> Path:
    return appdata / APP_CONFIG_SUBDIR / APP_CONFIG_FILE


def _read_app_config(home_path: Path, appdata_path: Path) -> dict:
    path = _app_config_path(home_path, appdata_path)
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError, TypeError):
        return {}
    return payload if isinstance(payload, dict) else {}


def _write_app_config(
    payload: dict,
    home_path: Path,
    appdata_path: Path,
) -> None:
    config_path = _app_config_path(home_path, appdata_path)
    config_path.parent.mkdir(parents=True, exist_ok=True)
    config_path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def load_last_database(
    home: str | Path | None = None,
    appdata: str | Path | None = None,
) -> Path | None:
    home_path = _home(home)
    appdata_path = _appdata_dir(home_path, appdata)
    payload = _read_app_config(home_path, appdata_path)

    last_db = payload.get("last_db")
    if not isinstance(last_db, str) or not last_db.strip():
        return None
    return Path(last_db).expanduser()


def save_last_database(
    db_path: str | Path,
    home: str | Path | None = None,
    appdata: str | Path | None = None,
) -> None:
    home_path = _home(home)
    appdata_path = _appdata_dir(home_path, appdata)
    payload = _read_app_config(home_path, appdata_path)
    payload["last_db"] = str(Path(db_path).expanduser())
    _write_app_config(payload, home_path, appdata_path)


def load_language(
    home: str | Path | None = None,
    appdata: str | Path | None = None,
) -> str:
    home_path = _home(home)
    appdata_path = _appdata_dir(home_path, appdata)
    payload = _read_app_config(home_path, appdata_path)
    return "en" if payload.get("language") == "en" else "zh"


def save_language(
    language: str,
    home: str | Path | None = None,
    appdata: str | Path | None = None,
) -> None:
    home_path = _home(home)
    appdata_path = _appdata_dir(home_path, appdata)
    payload = _read_app_config(home_path, appdata_path)
    payload["language"] = "en" if language == "en" else "zh"
    _write_app_config(payload, home_path, appdata_path)
