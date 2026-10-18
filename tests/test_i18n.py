from __future__ import annotations

from astrbot_conversation_manager import i18n
from astrbot_conversation_manager.importer import ImportManager
from astrbot_conversation_manager.paths import (
    load_language,
    load_last_database,
    save_language,
    save_last_database,
)


def test_static_translation():
    i18n.set_language("en")
    assert i18n.tr("打开数据库") == "Open database"
    assert i18n.tr("编辑消息 #{} ({})", 2, "user") == "Edit message #2 (user)"
    i18n.set_language("zh")
    assert i18n.tr("打开数据库") == "打开数据库"


def test_dynamic_translation():
    i18n.set_language("en")
    assert (
        i18n.translate_text("已加载 2 个对话 | demo.jsonl")
        == "Loaded 2 conversation(s) | demo.jsonl"
    )
    assert (
        i18n.translate_text(
            "文件包含 2 个对话，共 8 条消息。请在左侧选择目标对话。"
        )
        == "2 conversation(s), 8 message(s). Select the target conversation on the left."
    )
    assert (
        i18n.translate_text("数据库：自定义数据库 · demo\\data_v4.db")
        == "Database: 自定义数据库 · demo\\data_v4.db"
    )
    i18n.set_language("zh")


def test_reverse_translation():
    i18n.set_language("zh")
    try:
        assert i18n.translate_text("Data") == "数据管理"
        assert (
            i18n.translate_text("Database changed. Choose an export file.")
            == "数据库已切换，请选择导出文件"
        )
        assert (
            i18n.translate_text("Loaded 2 conversation(s) | demo.jsonl")
            == "已加载 2 个对话 | demo.jsonl"
        )
        assert (
            i18n.translate_text(
                "2 conversation(s), 8 message(s). Select the target conversation on the left."
            )
            == "文件包含 2 个对话，共 8 条消息。请在左侧选择目标对话。"
        )
        assert i18n.translate_text("2/4 selected (2 shown)") == "已勾选 2/4 条（显示 2 条）"
    finally:
        i18n.set_language("en")


def test_language_and_last_database_config(tmp_path):
    home = tmp_path / "home"
    appdata = tmp_path / "appdata"
    home.mkdir()
    appdata.mkdir()

    save_language("en", home=home, appdata=appdata)
    assert load_language(home=home, appdata=appdata) == "en"

    save_last_database("demo/data_v4.db", home=home, appdata=appdata)
    assert load_language(home=home, appdata=appdata) == "en"
    assert str(load_last_database(home=home, appdata=appdata)).endswith(
        "demo\\data_v4.db"
    ) or str(load_last_database(home=home, appdata=appdata)).endswith(
        "demo/data_v4.db"
    )

    save_language("zh", home=home, appdata=appdata)
    assert load_language(home=home, appdata=appdata) == "zh"


def test_user_id_translation():
    i18n.set_language("en")
    assert ImportManager.format_user_id("test:FriendMessage:123") == "Private:123"
    assert ImportManager.format_user_id("test:GroupMessage:456") == "Group:456"
    i18n.set_language("zh")
    assert ImportManager.format_user_id("test:FriendMessage:123") == "私聊:123"
