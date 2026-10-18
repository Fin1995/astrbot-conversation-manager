"""Small runtime translation layer for the Tkinter UI.

The source UI is written in Simplified Chinese.  Static widget texts are
translated in place when the user switches language, while dynamic status
strings go through :func:`tr` / :func:`translate_text`.
"""

from __future__ import annotations

import re
import tkinter as tk
from tkinter import ttk

LANGUAGES = {"zh": "简体中文", "en": "English"}
current = "zh"


EN = {
    # Main window
    "AstrBot 对话数据管理": "AstrBot Conversation Manager",
    "AstrBot 对话数据管理工具 {}": "AstrBot Conversation Manager {}",
    "打开数据库": "Open database",
    "自动检测": "Auto-detect",
    "数据管理": "Data",
    "导入对话": "Import",
    " 数据管理 ": " Data ",
    " 导入对话 ": " Import ",
    "内容": "Content",
    "数据库已切换": "Database changed",
    "数据库：{} · {}": "Database: {} · {}",
    "数据库：未选择": "Database: not selected",
    "已加载数据库：{}": "Database loaded: {}",
    "数据已更新": "Data updated",
    "数据已更新；备份：{}": "Data updated; backup: {}",
    "无法打开数据库": "Cannot open database",
    "提示": "Notice",
    "检测到 SQLite WAL 文件，AstrBot 或 Launcher 可能正在运行。\n建议先关闭它们再编辑。工具会在第一次写入前自动备份数据库。": (
        "A SQLite WAL file was found. AstrBot or the Launcher may be running.\n"
        "Close them before editing. The tool backs up the database before the first write."
    ),
    "未检测到数据库": "No database found",
    "没有在 AstrBot Desktop、Launcher、CLI 或当前目录中找到有效数据库。\n请点击“打开数据库”手动选择 data_v4.db 或 data_v3.db。": (
        "No valid database was found in AstrBot Desktop, Launcher, CLI, or the current directory.\n"
        "Click “Open database” and select data_v4.db or data_v3.db."
    ),
    "未检测到 AstrBot 数据库": "No AstrBot database detected",
    "未检测到 AstrBot 数据库；请点击“打开数据库”": (
        "No AstrBot database detected; click “Open database”"
    ),
    "选择 AstrBot 数据库": "Choose an AstrBot database",
    "选择 AstrBot 数据库文件": "Choose an AstrBot database file",
    "检测到多个 AstrBot 数据库，请选择要编辑的一个：": (
        "Multiple AstrBot databases found. Choose one to edit:"
    ),
    "来源": "Source",
    "路径": "Path",
    "打开": "Open",
    "取消": "Cancel",
    "SQLite 数据库": "SQLite database",
    "所有文件": "All files",
    "数据库": "Database",
    "自定义数据库": "Custom database",
    "AstrBot 源码目录": "AstrBot source",
    "AstrBot Desktop": "AstrBot Desktop",
    "AstrBot Launcher": "AstrBot Launcher",
    "AstrBot CLI": "AstrBot CLI",

    # Import tab
    "导出文件:": "Export file:",
    "选择文件": "Choose file",
    "文件中的对话": "Conversations in file",
    "消息预览（点击 ☑/☐ 勾选/取消）": "Message preview (click ☑/☐ to check/uncheck)",
    "显示:": "Show:",
    "用户": "User",
    "AI": "AI",
    "工具": "Tool",
    "按角色勾选:": "Check by role:",
    "导入": "Import",
    "角色": "Role",
    "消息内容": "Message",
    "类型": "Type",
    "全选": "Select all",
    "取消全选": "Clear all",
    "反选": "Invert",
    "高亮行:": "Highlighted rows:",
    "勾选": "Check",
    "取消勾选": "Uncheck",
    "数据库已切换，请选择导出文件": "Database changed. Choose an export file.",
    "导入选中消息": "Import selected messages",
    "文件包含 {} 个对话，共 {} 条消息": "{} conversation(s), {} message(s)",
    "文件包含 {} 个对话，共 {} 条消息。请在左侧选择目标对话。": (
        "{} conversation(s), {} message(s). Select the target conversation on the left."
    ),
    "已加载 {} 个对话 | {}": "Loaded {} conversation(s) | {}",
    "共 {} 条消息 | 已勾选 {} 条": "{} message(s) | {} selected",
    "已勾选 {}/{} 条（显示 {} 条）": "{}/{} selected ({} shown)",
    "加载失败": "Load failed",
    "无法解析文件:\n{}": "Cannot parse file:\n{}",
    "无法读取文件:\n{}": "Cannot read file:\n{}",
    "请选择导出文件": "Choose an export file",
    "选择 AstrBot 对话导出文件": "Choose an AstrBot export file",
    "AstrBot 导出文件": "AstrBot export",
    "已强制追加 {} 条消息到 {}": "Appended {} message(s) to {}",
    "已导入 {} 条消息": "Imported {} message(s)",
    "导入完成": "Import complete",
    "导入失败": "Import failed",
    "请先打开数据库文件": "Open a database first",
    "请先选择对话": "Select a conversation first",
    "请先选择消息": "Select messages first",
    "没有选中任何消息": "No messages selected",
    "导入方式": "Import mode",
    "合并到已有对话": "Merge into existing conversation",
    "替换已有对话": "Replace existing conversation",
    "新建对话": "New conversation",
    "目标对话不存在": "Target conversation does not exist",
    "已存在同名对话": "A conversation with this ID already exists",

    # Manage tab
    "搜索:": "Search:",
    "搜索": "Search",
    "刷新": "Refresh",
    "清空搜索": "Clear search",
    "数据库对话列表": "Database conversations",
    "对话 ID": "Conversation ID",
    "平台": "Platform",
    "消息数": "Messages",
    "创建时间": "Created",
    "更新时间": "Updated",
    "操作:": "Actions:",
    "编辑消息": "Edit message",
    "删除消息": "Delete message",
    "添加消息": "Add message",
    "展开": "Expand",
    "收起": "Collapse",
    "消息预览": "Message preview",
    "编辑此消息": "Edit this message",
    "删除选中消息": "Delete selected messages",
    "在此位置前插入": "Insert before",
    "在此位置后插入": "Insert after",
    "复制对话 ID": "Copy conversation ID",
    "重命名对话 ID": "Rename conversation ID",
    "删除对话": "Delete conversation",
    "刷新对话": "Refresh conversation",
    "已选择 {} 个对话": "{} conversation(s) selected",
    "共 {} 条消息": "{} message(s)",
    "已删除对话": "Conversation deleted",
    "已删除消息": "Message deleted",
    "已添加消息": "Message added",
    "已保存消息": "Message saved",
    "确认删除": "Confirm delete",
    "确定要删除这个对话吗？": "Delete this conversation?",
    "确定要删除选中的消息吗？": "Delete the selected messages?",
    "确定要重命名这个对话吗？": "Rename this conversation?",
    "新的对话 ID": "New conversation ID",
    "对话 ID 不能为空": "Conversation ID cannot be empty",
    "对话不存在": "Conversation does not exist",
    "目标 ID 已存在": "Target ID already exists",
    "已复制": "Copied",
    "复制失败": "Copy failed",

    # Message editor
    "编辑消息 #{} ({})": "Edit message #{} ({})",
    "保存": "Save",
    "角色:": "Role:",
    "AI 回复": "AI reply",
    "AI助手": "AI assistant",
    "直接编辑消息的完整 JSON（content 数组）:": (
        "Edit the complete message JSON (content array):"
    ),
    "文本编辑": "Text",
    "消息文本内容:": "Message text:",
    "JSON 编辑": "JSON",
    "直接编辑消息内容（JSON content 数组）:": (
        "Edit message content directly (JSON content array):"
    ),
    "JSON 错误": "JSON error",
    "JSON 格式无效:\n{}": "Invalid JSON:\n{}",
    "保存失败": "Save failed",
    "保存时发生错误:\n{}": "Error while saving:\n{}",
    "消息已保存": "Message saved",
    "编辑消息 #{} ({})": "Edit message #{} ({})",
    "错误": "Error",
    "确认": "Confirm",
    "警告": "Warning",

    # Database errors
    "数据库文件不存在: {}": "Database file not found: {}",
    "无法读取 SQLite 数据库: {}": "Cannot read SQLite database: {}",
    "数据库中没有找到 AstrBot 的 conversations 表，或缺少字段: {}": (
        "The AstrBot conversations table is missing or lacks columns: {}"
    ),
    "对话不存在: {}": "Conversation not found: {}",
    "消息索引超出范围: {}": "Message index out of range: {}",
    "conversation_id 不能为空": "conversation_id cannot be empty",
    "user_id 不能为空": "user_id cannot be empty",
    "content 必须是消息数组": "content must be a message array",
    "messages 必须是数组": "messages must be an array",
    "new_messages 必须是数组": "new_messages must be an array",
    "目标 ID 已存在: {}": "Target ID already exists: {}",
    "原对话不存在: {}": "Original conversation not found: {}",
    "新对话 ID 不能为空": "New conversation ID cannot be empty",
    "无法插入对话: {}": "Cannot insert conversation: {}",

    "{} | {} 条 | {}": "{} | {} messages | {}",
    "系统": "System",
    "含思考": "thinking",
    "调用: ": "Call: ",
    "(思考中)": "(thinking)",
    "(空)": "(empty)",
    "工具输出": "Tool output",
    "全部 {} 条消息 | 已勾选 {} 条 | 当前显示 {} 条": (
        "All {} message(s) | {} selected | {} shown"
    ),
    "请先在主窗口点击「打开数据库」选择数据库文件": (
        "Open a database from the main window first."
    ),
    "请先加载导出文件": "Load an export file first.",
    "请先在左侧选择一个对话": "Select a conversation on the left first.",
    "没有勾选任何消息": "No messages selected.",
    "对话已存在": "Conversation already exists",
    "对话 {}...\n数据库中已有 {} 条消息，你选中了 {} 条。": (
        "Conversation {}...\nThe database already has {} messages; you selected {}."
    ),
    "覆盖（替换为 {} 条）": "Overwrite (replace with {} messages)",
    "合并·去重（跳过完全相同的消息）": "Merge and deduplicate",
    "强制追加（保留重复）": "Force append (keep duplicates)",
    "取消（不导入）": "Cancel (do not import)",
    "已合并 {} 条消息到 {}": "Merged {} message(s) into {}",
    "（跳过 {} 条重复）": " ({} duplicate(s) skipped)",
    "完成": "Done",
    "已追加强制 {} 条消息": "Force-appended {} message(s)",
    "导入成功: {}/{} 条消息 → {}": "Import complete: {}/{} messages → {}",
    "成功导入 {} 条消息": "Imported {} message(s)",
    "导入失败": "Import failed",
    "数据库已切换，请选择对话": "Database changed. Select a conversation.",
    "请先选中一条消息": "Select a message first.",
    "请先选中要删除的消息": "Select messages to delete first.",
    "请先选择一个对话": "Select a conversation first.",
    "ID 不能为空": "ID cannot be empty",
    "修改失败": "Rename failed",
    "添加失败": "Add failed",
    "删除失败": "Delete failed",
    "确定要删除 {} 条选中的消息吗？\n此操作不可撤销。": (
        "Delete the {} selected message(s)?\nThis cannot be undone."
    ),
    "确定要删除整个对话吗？\n\n对话 ID: {}...\n消息数: {}\n\n此操作不可撤销。": (
        "Delete the entire conversation?\n\nConversation ID: {}...\nMessages: {}\n\nThis cannot be undone."
    ),
    "新消息已插入到位置 #{}": "New message inserted at #{}",
    "已复制: {}": "Copied: {}",
    "修改对话 ID": "Rename conversation ID",
    "当前 ID: {}": "Current ID: {}",
    "新 ID:": "New ID:",
    "确定": "OK",
    "ID 已更新: {}... → {}...": "ID updated: {}... → {}...",
    "对话 {}... 已删除": "Conversation {}... deleted",
    "JSON 格式无效:\n{}": "Invalid JSON:\n{}",
    "保存时发生错误:\n{}": "Error while saving:\n{}",

    # User ids
    "私聊": "Private",
    "群聊": "Group",
}

# Reverse lookup for switching English back to Chinese.  Several English
# labels are shared by different Chinese source strings, so the important
# ambiguous ones are pinned explicitly.
ZH = {value: key for key, value in EN.items() if value and value != key}
ZH.update(
    {
        "AstrBot Conversation Manager": "AstrBot 对话数据管理",
        "AstrBot Conversation Manager {}": "AstrBot 对话数据管理工具 {}",
        "Data": "数据管理",
        "Import": "导入",
        "Open database": "打开数据库",
        "Auto-detect": "自动检测",
        "Message": "消息内容",
        "Messages": "消息数",
        "Type": "类型",
        "Role": "角色",
        "User": "用户",
        "Tool": "工具",
        "Open": "打开",
        "Cancel": "取消",
        "Database": "数据库",
        "Search": "搜索",
        "Refresh": "刷新",
        "Created": "创建时间",
        "Updated": "更新时间",
        "Content": "内容",
        "Actions:": "操作:",
        "Message preview": "消息预览",
        "Custom database": "自定义数据库",
        "AstrBot source": "AstrBot 源码目录",
        "Database changed": "数据库已切换",
        "Database changed. Choose an export file.": "数据库已切换，请选择导出文件",
        "Database changed. Select a conversation.": "数据库已切换，请选择对话",
        "No database found": "未检测到数据库",
        "No AstrBot database detected": "未检测到 AstrBot 数据库",
        "Done": "完成",
        "Error": "错误",
        "Confirm": "确认",
        "Warning": "警告",
        "Notice": "提示",
        "Save": "保存",
        "Role:": "角色:",
        "AI assistant": "AI助手",
        "AI reply": "AI 回复",
        "Text": "文本编辑",
        "Message text:": "消息文本内容:",
        "Edit the complete message JSON (content array):": (
            "直接编辑消息的完整 JSON（content 数组）:"
        ),
        "JSON error": "JSON 错误",
        "Invalid JSON:\n{}": "JSON 格式无效:\n{}",
        "Save failed": "保存失败",
        "Error while saving:\n{}": "保存时发生错误:\n{}",
        "Choose an AstrBot database": "选择 AstrBot 数据库",
        "Choose an AstrBot database file": "选择 AstrBot 数据库文件",
        "Multiple AstrBot databases found. Choose one to edit:": (
            "检测到多个 AstrBot 数据库，请选择要编辑的一个："
        ),
        "Source": "来源",
        "Path": "路径",
        "SQLite database": "SQLite 数据库",
        "All files": "所有文件",
        "Choose an AstrBot export file": "选择 AstrBot 对话导出文件",
        "AstrBot export": "AstrBot 导出文件",
        "Load failed": "加载失败",
        "Import failed": "导入失败",
        "Import selected messages": "导入选中消息",
        "Export file:": "导出文件:",
        "Choose file": "选择文件",
        "Conversations in file": "文件中的对话",
        "Show:": "显示:",
        "Check by role:": "按角色勾选:",
        "Select all": "全选",
        "Clear all": "取消全选",
        "Invert": "反选",
        "Highlighted rows:": "高亮行:",
        "Check": "勾选",
        "Uncheck": "取消勾选",
        "Search:": "搜索:",
        "Clear search": "清空搜索",
        "Database conversations": "数据库对话列表",
        "Conversation ID": "对话 ID",
        "Platform": "平台",
        "Edit message": "编辑消息",
        "Delete message": "删除消息",
        "Add message": "添加消息",
        "Expand": "展开",
        "Collapse": "收起",
        "Edit this message": "编辑此消息",
        "Delete selected messages": "删除选中消息",
        "Insert before": "在此位置前插入",
        "Insert after": "在此位置后插入",
        "Copy conversation ID": "复制对话 ID",
        "Rename conversation ID": "重命名对话 ID",
        "Delete conversation": "删除对话",
        "Refresh conversation": "刷新对话",
    }
)


_PATTERNS = [
    (re.compile(r"^数据库：(.+)$"), r"Database: \1"),
    (re.compile(r"^已加载数据库：(.+)$"), r"Database loaded: \1"),
    (re.compile(r"^数据已更新；备份：(.+)$"), r"Data updated; backup: \1"),
    (re.compile(r"^已加载 (\d+) 个对话 \| (.+)$"), r"Loaded \1 conversation(s) | \2"),
    (re.compile(r"^文件包含 (\d+) 个对话，共 (\d+) 条消息$"), r"\1 conversation(s), \2 message(s)"),
    (re.compile(r"^文件包含 (\d+) 个对话，共 (\d+) 条消息。请在左侧选择目标对话。$"), r"\1 conversation(s), \2 message(s). Select the target conversation on the left."),
    (re.compile(r"^共 (\d+) 条消息 \| 已勾选 (\d+) 条$"), r"\1 message(s) | \2 selected"),
    (re.compile(r"^已勾选 (\d+)/(\d+) 条（显示 (\d+) 条）$"), r"\1/\2 selected (\3 shown)"),
    (re.compile(r"^已选择 (\d+) 个对话$"), r"\1 conversation(s) selected"),
    (re.compile(r"^共 (\d+) 条消息$"), r"\1 message(s)"),
    (re.compile(r"^已强制追加 (\d+) 条消息到 (.+)$"), r"Appended \1 message(s) to \2"),
    (re.compile(r"^已导入 (\d+) 条消息$"), r"Imported \1 message(s)"),
    (re.compile(r"^已删除 (\d+) 条消息$"), r"Deleted \1 message(s)"),
    (re.compile(r"^已选择 (\d+) 条消息$"), r"\1 message(s) selected"),
    (re.compile(r"^新消息已插入到位置 #(\d+)$"), r"New message inserted at #\1"),
    (re.compile(r"^已复制: (.+)$"), r"Copied: \1"),
    (re.compile(r"^ID 已更新: (.+) → (.+)$"), r"ID updated: \1 → \2"),
    (re.compile(r"^对话 (.+) 已删除$"), r"Conversation \1 deleted"),
    (re.compile(r"^数据库文件不存在: (.+)$"), r"Database file not found: \1"),
    (re.compile(r"^无法读取 SQLite 数据库: (.+)$"), r"Cannot read SQLite database: \1"),
    (re.compile(r"^数据库中没有找到 AstrBot 的 conversations 表，或缺少字段: (.+)$"), r"The AstrBot conversations table is missing or lacks columns: \1"),
    (re.compile(r"^对话不存在: (.+)$"), r"Conversation not found: \1"),
    (re.compile(r"^消息索引超出范围: (.+)$"), r"Message index out of range: \1"),
    (re.compile(r"^目标 ID 已存在: (.+)$"), r"Target ID already exists: \1"),
    (re.compile(r"^原对话不存在: (.+)$"), r"Original conversation not found: \1"),
    (re.compile(r"^无法插入对话: (.+)$"), r"Cannot insert conversation: \1"),
]


_ZH_PATTERNS = [
    (re.compile(r"^Database: (.+)$"), r"数据库：\1"),
    (re.compile(r"^Database loaded: (.+)$"), r"已加载数据库：\1"),
    (re.compile(r"^Data updated; backup: (.+)$"), r"数据已更新；备份：\1"),
    (re.compile(r"^Loaded (\d+) conversation\(s\) \| (.+)$"), r"已加载 \1 个对话 | \2"),
    (re.compile(r"^(\d+) conversation\(s\), (\d+) message\(s\)\. Select the target conversation on the left\.$"), r"文件包含 \1 个对话，共 \2 条消息。请在左侧选择目标对话。"),
    (re.compile(r"^(\d+) conversation\(s\), (\d+) message\(s\)$"), r"文件包含 \1 个对话，共 \2 条消息"),
    (re.compile(r"^(\d+) message\(s\) \| (\d+) selected$"), r"共 \1 条消息 | 已勾选 \2 条"),
    (re.compile(r"^(\d+)/(\d+) selected \((\d+) shown\)$"), r"已勾选 \1/\2 条（显示 \3 条）"),
    (re.compile(r"^All (\d+) message\(s\) \| (\d+) selected \| (\d+) shown$"), r"全部 \1 条消息 | 已勾选 \2 条 | 当前显示 \3 条"),
    (re.compile(r"^Database changed$"), r"数据库已切换"),
    (re.compile(r"^Database changed\. Choose an export file\.$"), r"数据库已切换，请选择导出文件"),
    (re.compile(r"^Database changed\. Select a conversation\.$"), r"数据库已切换，请选择对话"),
    (re.compile(r"^Imported (\d+) message\(s\)$"), r"已导入 \1 条消息"),
    (re.compile(r"^Merged (\d+) message\(s\) into (.+)$"), r"已合并 \1 条消息到 \2"),
    (re.compile(r"^Appended (\d+) message\(s\) to (.+)$"), r"已强制追加 \1 条消息到 \2"),
    (re.compile(r"^Deleted (\d+) message\(s\)$"), r"已删除 \1 条消息"),
    (re.compile(r"^Copied: (.+)$"), r"已复制: \1"),
    (re.compile(r"^ID updated: (.+) → (.+)$"), r"ID 已更新: \1 → \2"),
    (re.compile(r"^Conversation (.+) deleted$"), r"对话 \1 已删除"),
    (re.compile(r"^New message inserted at #(\d+)$"), r"新消息已插入到位置 #\1"),
    (re.compile(r"^Force-appended (\d+) message\(s\)$"), r"已追加强制 \1 条消息"),
    (re.compile(r"^Import complete: (.+)$"), r"导入成功: \1"),
    (re.compile(r"^(\d+) conversation\(s\) selected$"), r"已选择 \1 个对话"),
    (re.compile(r"^(\d+) message\(s\)$"), r"共 \1 条消息"),
]


def set_language(language: str) -> None:
    global current
    current = "en" if language == "en" else "zh"


def tr(text: str, *args, **kwargs) -> str:
    """Translate a source string, optionally formatting placeholders."""

    if current != "en":
        translated = text
    else:
        translated = EN.get(text, text)

    if args or kwargs:
        try:
            translated = translated.format(*args, **kwargs)
        except (IndexError, KeyError):
            pass
    return translated


def translate_text(text):
    """Translate a complete static or dynamic string."""

    if not isinstance(text, str):
        return text

    table = EN if current == "en" else ZH
    patterns = _PATTERNS if current == "en" else _ZH_PATTERNS

    translated = table.get(text)
    if translated is not None:
        return translated

    for pattern, replacement in patterns:
        if pattern.match(text):
            return pattern.sub(replacement, text)

    return text


def _translate_widget(widget) -> None:
    # Widget text option.
    try:
        text = widget.cget("text")
    except Exception:
        text = None
    if isinstance(text, str) and text:
        translated = translate_text(text)
        if translated != text:
            try:
                widget.configure(text=translated)
            except Exception:
                pass

    # StringVar-backed text.
    try:
        variable_name = widget.cget("textvariable")
    except Exception:
        variable_name = None
    if variable_name:
        try:
            value = widget.getvar(variable_name)
            translated = translate_text(value)
            if translated != value:
                widget.setvar(variable_name, translated)
        except Exception:
            pass

    # Notebook tabs.
    if isinstance(widget, ttk.Notebook):
        try:
            for tab_id in widget.tabs():
                tab_text = widget.tab(tab_id, "text")
                translated = translate_text(tab_text)
                if translated != tab_text:
                    widget.tab(tab_id, text=translated)
        except Exception:
            pass

    # Treeview headings.
    if isinstance(widget, ttk.Treeview):
        try:
            for column in widget["columns"]:
                heading = widget.heading(column)
                heading_text = heading.get("text", "")
                translated = translate_text(heading_text)
                if translated != heading_text:
                    widget.heading(column, text=translated)
        except Exception:
            pass

    # Menu entries.
    if isinstance(widget, tk.Menu):
        try:
            end = widget.index("end")
        except Exception:
            end = None
        if end is not None:
            for index in range(end + 1):
                try:
                    label = widget.entrycget(index, "label")
                except Exception:
                    continue
                translated = translate_text(label)
                if translated != label:
                    try:
                        widget.entryconfigure(index, label=translated)
                    except Exception:
                        pass


def apply_language(root) -> None:
    """Translate an existing widget tree in place."""

    if isinstance(root, (tk.Tk, tk.Toplevel)):
        try:
            title = root.title()
            translated = translate_text(title)
            if translated != title:
                root.title(translated)
        except Exception:
            pass

    for widget in root.winfo_children():
        _translate_widget(widget)
        apply_language(widget)
