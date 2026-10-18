from __future__ import annotations

import json
from pathlib import Path

from astrbot_conversation_manager.paths import (
    detect_databases,
    load_last_database,
    save_last_database,
)


def _context(tmp_path):
    home = tmp_path / "home"
    appdata = tmp_path / "appdata"
    cwd = tmp_path / "work"
    home.mkdir()
    appdata.mkdir()
    cwd.mkdir()
    return home, appdata, cwd


def _detect(home, appdata, cwd, **kwargs):
    return detect_databases(
        home=home,
        appdata=appdata,
        cwd=cwd,
        env=kwargs.pop("env", {}),
        include_saved=kwargs.pop("include_saved", False),
        **kwargs,
    )


def test_detects_desktop(tmp_path, make_db):
    home, appdata, cwd = _context(tmp_path)
    db = make_db("data_v4.db")
    target = home / ".astrbot" / "data" / "data_v4.db"
    target.parent.mkdir(parents=True)
    db.replace(target)

    found = _detect(home, appdata, cwd)

    assert len(found) == 1
    assert found[0].kind == "desktop"
    assert found[0].path == target.resolve()


def test_detects_launcher_instances(tmp_path, make_db):
    home, appdata, cwd = _context(tmp_path)
    target = (
        home
        / ".astrbot_launcher"
        / "instances"
        / "instance-a"
        / "core"
        / "data"
        / "data_v4.db"
    )
    target.parent.mkdir(parents=True)
    make_db("data_v4.db").replace(target)

    found = _detect(home, appdata, cwd)

    assert len(found) == 1
    assert found[0].kind == "launcher"
    assert found[0].instance == "instance-a"
    assert found[0].path == target.resolve()


def test_detects_launcher_custom_data_dir(tmp_path, make_db):
    home, appdata, cwd = _context(tmp_path)
    custom = tmp_path / "custom-launcher"
    target = custom / "instances" / "custom" / "core" / "data" / "data_v4.db"
    target.parent.mkdir(parents=True)
    make_db("data_v4.db").replace(target)

    config = appdata / "com.github.raven95676.astrbot-launcher"
    config.mkdir(parents=True)
    (config / ".data-dir.json").write_text(
        json.dumps({"data_dir": str(custom)}),
        encoding="utf-8",
    )

    found = _detect(home, appdata, cwd)

    assert len(found) == 1
    assert found[0].kind == "launcher"
    assert found[0].path == target.resolve()


def test_detects_cli_and_source(tmp_path, make_db):
    home, appdata, cwd = _context(tmp_path)
    cli = home / ".local" / "share" / "astrbot" / "data" / "data_v4.db"
    cli.parent.mkdir(parents=True)
    make_db("data_v4.db").replace(cli)

    source = cwd / "data" / "data_v4.db"
    source.parent.mkdir(parents=True)
    make_db("data_v4.db").replace(source)

    found = _detect(home, appdata, cwd)

    assert {item.kind for item in found} == {"cli", "source"}
    assert {item.path for item in found} == {cli.resolve(), source.resolve()}


def test_detects_astrbot_root_env(tmp_path, make_db):
    home, appdata, cwd = _context(tmp_path)
    root = tmp_path / "AstrBot"
    target = root / "data" / "data_v4.db"
    target.parent.mkdir(parents=True)
    make_db("data_v4.db").replace(target)

    found = _detect(home, appdata, cwd, env={"ASTRBOT_ROOT": str(root)})

    assert len(found) == 1
    assert found[0].kind == "source"
    assert found[0].path == target.resolve()


def test_explicit_database_and_saved_path(tmp_path, make_db):
    home, appdata, cwd = _context(tmp_path)
    explicit = tmp_path / "explicit" / "data_v4.db"
    explicit.parent.mkdir()
    make_db("data_v4.db").replace(explicit)

    found = _detect(
        home,
        appdata,
        cwd,
        env={"ASTRBOT_CONVERSATION_DB": str(explicit)},
    )
    assert found[0].kind == "custom"
    assert found[0].path == explicit.resolve()

    save_last_database(explicit, home=home, appdata=appdata)
    assert load_last_database(home=home, appdata=appdata) == explicit

    found = _detect(home, appdata, cwd, include_saved=True)
    assert found[0].kind == "custom"
    assert found[0].path == explicit.resolve()


def test_invalid_database_is_skipped(tmp_path, make_db):
    home, appdata, cwd = _context(tmp_path)
    bad = home / ".astrbot" / "data" / "data_v4.db"
    bad.parent.mkdir(parents=True)
    make_db("data_v4.db", include_schema=False).replace(bad)

    assert _detect(home, appdata, cwd) == []


def test_no_hardcoded_user_path(tmp_path, make_db):
    home, appdata, cwd = _context(tmp_path)
    target = home / ".astrbot" / "data" / "data_v4.db"
    target.parent.mkdir(parents=True)
    make_db("data_v4.db").replace(target)

    found = _detect(home, appdata, cwd)
    assert str(found[0].path).startswith(str(home.resolve()))
