"""AstrBot Conversation Manager desktop UI.

Run with ``python -m astrbot_conversation_manager`` or ``python run.pyw``.
"""

from __future__ import annotations

import argparse
import ctypes
import json
import os
import tkinter as tk
from ctypes import wintypes
from datetime import datetime, timezone, timedelta
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

from . import __version__
from . import i18n
from .db import ConversationDB, InvalidDatabaseError
from .i18n import apply_language, set_language, translate_text, tr
from .importer import ConversationImportError, ImportManager
from .paths import (
    DatabaseCandidate,
    detect_databases,
    load_language,
    save_language,
    save_last_database,
)

CST = timezone(timedelta(hours=8))  # 北京时间

# ============================================================
# 工具函数
# ============================================================


def extract_message_text(msg: dict) -> str:
    """从消息 JSON 中提取可读文本"""
    content = msg.get("content", [])

    # tool 消息的 content 是纯字符串（工具执行结果）
    if isinstance(content, str):
        return content

    if not isinstance(content, list):
        return str(content) if content else ""

    texts = []
    for block in content:
        if not isinstance(block, dict):
            continue
        if block.get("type") == "text":
            t = block.get("text", "")
            if isinstance(t, str):
                texts.append(t)
        elif block.get("type") == "think":
            # 思考链不显示
            pass
    return "".join(texts)


def extract_full_content_text(content: list | str) -> str:
    """提取 content 中所有文本（用于编辑）"""
    # tool 消息的 content 是纯字符串
    if isinstance(content, str):
        return content
    if not isinstance(content, list):
        return str(content) if content else ""
    result = []
    for block in content:
        if not isinstance(block, dict):
            continue
        if block.get("type") == "text":
            result.append(block.get("text", ""))
    return "\n".join(result)


def build_content_from_text(text: str, role: str = "") -> list:
    """从纯文本构建 content JSON 数组"""
    return [{"type": "text", "text": text}]


def timestamp_to_display(ts) -> str:
    """时间戳或 datetime 字符串 → 显示格式"""
    if ts is None:
        return ""
    if isinstance(ts, (int, float)):
        try:
            return datetime.fromtimestamp(ts, tz=CST).strftime("%Y-%m-%d %H:%M:%S")
        except (OSError, ValueError):
            return str(ts)
    if isinstance(ts, str) and len(ts) > 19:
        # AstrBot stores microseconds; the table only needs seconds.
        return ts.split(".", 1)[0]
    return str(ts)


def timestamp_to_db(ts):
    """输入时间值 → database datetime 字符串"""
    if ts is None:
        return datetime.now(CST).strftime("%Y-%m-%d %H:%M:%S.%f")
    if isinstance(ts, (int, float)):
        try:
            return datetime.fromtimestamp(ts, tz=CST).strftime("%Y-%m-%d %H:%M:%S.%f")
        except (OSError, ValueError):
            pass
    return str(ts)


def truncate(text: str, max_len: int = 60) -> str:
    """截断文本"""
    text = text.replace("\n", " ").replace("\r", "")
    if len(text) <= max_len:
        return text
    return text[: max_len - 3] + "..."


def get_work_area(window) -> tuple[int, int, int, int]:
    """Return the Windows work area, excluding the taskbar."""

    try:
        rect = wintypes.RECT()
        if ctypes.windll.user32.SystemParametersInfoW(
            0x0030, 0, ctypes.byref(rect), 0
        ):
            return rect.left, rect.top, rect.right, rect.bottom
    except Exception:
        pass
    return 0, 0, window.winfo_screenwidth(), window.winfo_screenheight()


def center_window(window: tk.Toplevel, parent=None):
    """将弹窗居中于父窗口"""
    if parent is None:
        parent = window.master
    # 向上查找顶层 Tk 窗口
    while not isinstance(parent, tk.Tk) and parent is not None:
        parent = parent.master
    if parent is None:
        return
    parent.update_idletasks()
    window.update_idletasks()
    pw = parent.winfo_width()
    ph = parent.winfo_height()
    px = parent.winfo_rootx()
    py = parent.winfo_rooty()
    ww = window.winfo_width()
    wh = window.winfo_height()
    x = px + (pw - ww) // 2
    y = py + (ph - wh) // 2
    window.geometry(f"+{x}+{y}")


# ============================================================
# 数据访问层
# ============================================================




class MessageEditDialog(tk.Toplevel):
    """消息编辑弹窗"""

    def __init__(self, parent, message: dict, index: int):
        super().__init__(parent)
        self.message = message
        self.index = index
        self.result = None  # 返回编辑后的消息 dict，或 None（取消）

        role = message.get("role", "user")
        is_tool = (role == "tool")
        self.title(tr("编辑消息 #{} ({})", index + 1, role))
        self.geometry("700x450")
        self.minsize(500, 350)
        self.resizable(True, True)

        # 底部按钮（先创建，确保始终可见）
        btn_frame = ttk.Frame(self)
        btn_frame.pack(side=tk.BOTTOM, fill=tk.X, padx=10, pady=(5, 10))
        ttk.Button(btn_frame, text="保存", command=self._on_save).pack(
            side=tk.RIGHT, padx=5
        )
        ttk.Button(btn_frame, text="取消", command=self.destroy).pack(side=tk.RIGHT)

        # 顶层框架
        top = ttk.Frame(self)
        top.pack(fill=tk.BOTH, expand=True, padx=10, pady=(10, 0))

        # 角色选择
        role_frame = ttk.Frame(top)
        role_frame.pack(fill=tk.X, pady=(0, 5))
        ttk.Label(role_frame, text="角色:").pack(side=tk.LEFT)
        self.role_var = tk.StringVar(value=role)
        ttk.Radiobutton(
            role_frame, text="用户", variable=self.role_var, value="user"
        ).pack(side=tk.LEFT, padx=5)
        ttk.Radiobutton(
            role_frame, text="AI助手", variable=self.role_var, value="assistant"
        ).pack(side=tk.LEFT, padx=5)
        ttk.Radiobutton(
            role_frame, text="工具", variable=self.role_var, value="tool"
        ).pack(side=tk.LEFT, padx=5)

        # 标签页：简单模式 / JSON 模式
        self.notebook = ttk.Notebook(top)
        self.notebook.pack(fill=tk.BOTH, expand=True)

        # --- 简单文本模式 ---
        simple_frame = ttk.Frame(self.notebook)
        self.notebook.add(simple_frame, text="文本编辑")

        ttk.Label(simple_frame, text="消息文本内容:").pack(anchor=tk.W, pady=(5, 0))
        self.text_editor = tk.Text(simple_frame, wrap=tk.WORD, font=("Microsoft YaHei", 10))
        self.text_editor.pack(fill=tk.BOTH, expand=True, pady=5)

        # 填充现有文本
        current_text = extract_full_content_text(message.get("content", []))
        self.text_editor.insert("1.0", current_text)

        # --- JSON 模式 ---
        json_frame = ttk.Frame(self.notebook)
        self.notebook.add(json_frame, text="JSON 编辑")

        ttk.Label(
            json_frame,
            text="直接编辑消息的完整 JSON（content 数组）:",
        ).pack(anchor=tk.W, pady=(5, 0))
        self.json_editor = tk.Text(json_frame, wrap=tk.WORD, font=("Consolas", 10))
        self.json_editor.pack(fill=tk.BOTH, expand=True, pady=5)

        content_json = json.dumps(message.get("content", []), ensure_ascii=False, indent=2)
        self.json_editor.insert("1.0", content_json)

        # tool 消息默认切到 JSON 模式（content 是字符串）
        if is_tool:
            self.notebook.select(1)

        apply_language(self)
        center_window(self, parent)

        self.transient(parent)
        self.grab_set()
        self.protocol("WM_DELETE_WINDOW", self.destroy)

    def _on_save(self):
        """保存编辑结果"""
        try:
            current_tab = self.notebook.index(self.notebook.select())
            role = self.role_var.get()

            if current_tab == 1:  # JSON 模式
                try:
                    content = json.loads(self.json_editor.get("1.0", "end-1c"))
                except (json.JSONDecodeError, ValueError) as e:
                    messagebox.showerror(tr("JSON 错误"), tr("JSON 格式无效:\n{}", e), parent=self)
                    return
            else:  # 文本模式
                text = self.text_editor.get("1.0", "end-1c").strip()
                if role == "tool":
                    content = text
                else:
                    content = build_content_from_text(text)

            self.result = {"role": role, "content": content}
            self.grab_release()
            self.destroy()
        except Exception as e:
            messagebox.showerror(tr("保存失败"), tr("保存时发生错误:\n{}", e), parent=self)


# ============================================================
# GUI: 导入标签页
# ============================================================


class ImportTab(ttk.Frame):
    """导入对话标签页"""

    def __init__(self, parent, db: ConversationDB, on_imported=None):
        super().__init__(parent)
        self.db = db
        self.on_imported = on_imported  # 导入完成后的回调
        self.conversations = []  # 文件中解析出的对话
        self.selected_indices: set[int] = set()  # 勾选的消息索引
        self._total_msg_count = 0  # 真实消息总数（不受过滤影响）
        self.file_summary_var = tk.StringVar(value="")

        # 角色过滤状态
        self.show_user = tk.BooleanVar(value=True)
        self.show_assistant = tk.BooleanVar(value=True)
        self.show_tool = tk.BooleanVar(value=True)

        self._build_ui()

    def update_db(self, db: ConversationDB):
        """切换数据库引用"""
        self.db = db
        self.status_var.set(tr("数据库已切换，请选择导出文件"))

    def _build_ui(self):
        # === 顶部：文件选择 ===
        file_frame = ttk.Frame(self)
        file_frame.pack(fill=tk.X, padx=10, pady=10)

        ttk.Label(file_frame, text="导出文件:").pack(side=tk.LEFT)
        self.file_path_var = tk.StringVar()
        ttk.Entry(
            file_frame, textvariable=self.file_path_var, state="readonly", width=60
        ).pack(side=tk.LEFT, fill=tk.X, expand=True, padx=5)
        ttk.Button(file_frame, text="选择文件", command=self._select_file).pack(
            side=tk.LEFT
        )

        ttk.Label(
            self,
            textvariable=self.file_summary_var,
            foreground="gray",
            anchor=tk.W,
        ).pack(fill=tk.X, padx=10)

        # === 中间：对话信息 + 消息列表 ===
        paned = ttk.PanedWindow(self, orient=tk.HORIZONTAL)
        paned.pack(fill=tk.BOTH, expand=True, padx=10, pady=5)

        # 左侧：对话概要
        left_frame = ttk.LabelFrame(paned, text="文件中的对话")
        paned.add(left_frame, weight=1)

        self.conv_listbox = tk.Listbox(left_frame, exportselection=False, width=30)
        self.conv_listbox.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)
        self.conv_listbox.bind("<<ListboxSelect>>", self._on_conv_select)

        # 右侧：消息列表
        right_frame = ttk.LabelFrame(
            paned, text="消息预览（点击 ☑/☐ 勾选/取消）"
        )
        paned.add(right_frame, weight=4)

        # 过滤 + 选择工具栏（两行）
        filter_bar = ttk.Frame(right_frame)
        filter_bar.pack(fill=tk.X, padx=5, pady=(5, 0))

        f_row1 = ttk.Frame(filter_bar)
        f_row1.pack(fill=tk.X)
        ttk.Label(f_row1, text="显示:").pack(side=tk.LEFT)
        ttk.Checkbutton(
            f_row1, text="用户", variable=self.show_user, command=self._refilter
        ).pack(side=tk.LEFT, padx=3)
        ttk.Checkbutton(
            f_row1, text="AI", variable=self.show_assistant, command=self._refilter
        ).pack(side=tk.LEFT, padx=3)
        ttk.Checkbutton(
            f_row1, text="工具", variable=self.show_tool, command=self._refilter
        ).pack(side=tk.LEFT, padx=3)
        ttk.Separator(f_row1, orient=tk.VERTICAL).pack(
            side=tk.LEFT, fill=tk.Y, padx=4, pady=1
        )
        self.import_count_var = tk.StringVar(value="")
        ttk.Label(
            f_row1, textvariable=self.import_count_var, foreground="#0066CC"
        ).pack(side=tk.LEFT, padx=3)

        f_row2 = ttk.Frame(filter_bar)
        f_row2.pack(fill=tk.X)
        ttk.Label(f_row2, text="按角色勾选:").pack(side=tk.LEFT)
        ttk.Button(
            f_row2,
            text="用户",
            command=lambda: self._select_by_role("user"),
            width=4,
        ).pack(side=tk.LEFT, padx=1)
        ttk.Button(
            f_row2,
            text="AI",
            command=lambda: self._select_by_role("assistant"),
            width=3,
        ).pack(side=tk.LEFT, padx=1)
        ttk.Button(
            f_row2,
            text="工具",
            command=lambda: self._select_by_role("tool"),
            width=4,
        ).pack(side=tk.LEFT, padx=1)

        # 底部操作栏先 pack，消息树才能占满剩余宽度。
        btn_bar = ttk.Frame(right_frame)
        btn_bar.pack(side=tk.BOTTOM, fill=tk.X, padx=5, pady=(0, 5))

        row1 = ttk.Frame(btn_bar)
        row1.pack(fill=tk.X)
        ttk.Button(row1, text="全选", command=self._select_all).pack(
            side=tk.LEFT, padx=1
        )
        ttk.Button(row1, text="取消全选", command=self._deselect_all).pack(
            side=tk.LEFT, padx=1
        )
        ttk.Button(row1, text="反选", command=self._invert_selection).pack(
            side=tk.LEFT, padx=1
        )
        ttk.Separator(row1, orient=tk.VERTICAL).pack(
            side=tk.LEFT, fill=tk.Y, padx=4, pady=1
        )
        ttk.Label(row1, text="高亮行:").pack(side=tk.LEFT)
        ttk.Button(
            row1, text="勾选", command=self._check_selected, width=4
        ).pack(side=tk.LEFT, padx=1)
        ttk.Button(
            row1, text="取消勾选", command=self._uncheck_selected, width=6
        ).pack(side=tk.LEFT, padx=1)

        row2 = ttk.Frame(btn_bar)
        row2.pack(fill=tk.X)
        self.selection_count_var = tk.StringVar(value="")
        ttk.Label(
            row2, textvariable=self.selection_count_var, foreground="gray"
        ).pack(side=tk.LEFT)

        # 消息 Treeview
        columns = ("check", "index", "role", "preview", "type")
        self.msg_tree = ttk.Treeview(
            right_frame,
            columns=columns,
            show="headings",
            selectmode="extended",
            height=8,
        )
        self.msg_tree.heading("check", text="导入")
        self.msg_tree.heading("index", text="#")
        self.msg_tree.heading("role", text="角色")
        self.msg_tree.heading("preview", text="消息内容")
        self.msg_tree.heading("type", text="类型")

        self.msg_tree.column("check", width=45, anchor=tk.CENTER, stretch=False)
        self.msg_tree.column("index", width=35, anchor=tk.CENTER, stretch=False)
        self.msg_tree.column("role", width=55, anchor=tk.CENTER, stretch=False)
        self.msg_tree.column("preview", width=320, stretch=True)
        self.msg_tree.column("type", width=140, anchor=tk.CENTER, stretch=False)

        self.msg_tree.bind("<ButtonRelease-1>", self._on_checkbox_click)

        scrollbar = ttk.Scrollbar(right_frame, command=self.msg_tree.yview)
        self.msg_tree.configure(yscrollcommand=scrollbar.set)
        self.msg_tree.tag_configure("system_reminder", foreground="gray")
        self.msg_tree.tag_configure("role_user", foreground="gray")
        self.msg_tree.tag_configure("role_tool", foreground="#0066CC")

        self.msg_tree.pack(
            side=tk.LEFT, fill=tk.BOTH, expand=True, padx=5, pady=5
        )
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y, pady=5)

        bottom_frame = ttk.Frame(self)
        bottom_frame.pack(fill=tk.X, padx=10, pady=10)

        self.status_var = tk.StringVar(value="请选择导出文件")
        ttk.Label(bottom_frame, textvariable=self.status_var).pack(
            side=tk.LEFT, fill=tk.X, expand=True
        )
        ttk.Button(
            bottom_frame, text="导入选中消息", command=self._do_import
        ).pack(side=tk.RIGHT, padx=5)

    # ---- 文件加载 ----

    def _select_file(self):
        filepath = filedialog.askopenfilename(
            title="选择 AstrBot 对话导出文件",
            filetypes=[
                ("AstrBot 导出文件", "*.jsonl *.json"),
                ("所有文件", "*.*"),
            ],
        )
        if not filepath:
            return
        self.load_file(filepath)

    def load_file(self, filepath: str):
        """Load an export file into the import preview."""
        display_name = Path(filepath).name
        self.file_path_var.set(display_name)
        try:
            self.conversations = ImportManager.load_file(filepath)
            total_messages = sum(
                len(conversation.get("content", []))
                for conversation in self.conversations
                if isinstance(conversation.get("content"), list)
            )
            self.file_summary_var.set(
                tr(
                    "文件包含 {} 个对话，共 {} 条消息。请在左侧选择目标对话。",
                    len(self.conversations),
                    total_messages,
                )
            )
            self._populate_conv_list()
            if self.conversations:
                self.conv_listbox.selection_set(0)
                self._show_messages(self.conversations[0])
            self.status_var.set(
                tr(
                    "已加载 {} 个对话 | {}",
                    len(self.conversations),
                    display_name,
                )
            )
        except ConversationImportError as exc:
            messagebox.showerror(
                tr("加载失败"), tr("无法解析文件:\n{}", exc)
            )
            self.conversations = []
            self.file_summary_var.set("")
            self._populate_conv_list()
        except OSError as exc:
            messagebox.showerror(
                tr("加载失败"), tr("无法读取文件:\n{}", exc)
            )
            self.conversations = []
            self.file_summary_var.set("")
            self._populate_conv_list()

    def retranslate(self):
        self.status_var.set(translate_text(self.status_var.get()))
        self.import_count_var.set(translate_text(self.import_count_var.get()))
        self.selection_count_var.set(
            translate_text(self.selection_count_var.get())
        )
        self.file_summary_var.set(
            translate_text(self.file_summary_var.get())
        )
        selection = self.conv_listbox.curselection()
        self._populate_conv_list()
        if selection and selection[0] < len(self.conversations):
            self.conv_listbox.selection_set(selection[0])
            self._show_messages(self.conversations[selection[0]])

    def _populate_conv_list(self):
        self.conv_listbox.delete(0, tk.END)
        for conv in self.conversations:
            cid = conv.get("conversation_id", "?")
            msg_count = len(conv.get("content", []))
            user_label = ImportManager.format_user_id(conv.get("user_id", "?"))
            created = timestamp_to_display(conv.get("created_at"))
            self.conv_listbox.insert(
                tk.END,
                tr("{} | {} 条 | {}", user_label, msg_count, created),
            )

    # ---- 消息显示 ----

    def _on_conv_select(self, event):
        selection = self.conv_listbox.curselection()
        if not selection:
            return
        idx = selection[0]
        if idx >= len(self.conversations):
            return
        conv = self.conversations[idx]
        self._show_messages(conv)

    def _refilter(self):
        """角色过滤变化时重绘消息列表（保留已有勾选）"""
        if self.conversations:
            sel = self.conv_listbox.curselection()
            if sel and sel[0] < len(self.conversations):
                self._show_messages(self.conversations[sel[0]], preserve_selection=True)

    def _show_messages(self, conv: dict, preserve_selection=False):
        """在消息树中显示对话消息，受角色过滤控制。
        preserve_selection=True 时不清除已勾选状态（用于过滤重绘）。
        """
        self.msg_tree.delete(*self.msg_tree.get_children())
        if not preserve_selection:
            self.selected_indices.clear()

        messages = conv.get("content", [])
        if not isinstance(messages, list):
            messages = []
        self._total_msg_count = len(messages)  # 真实总数（不受过滤影响）

        for i, msg in enumerate(messages):
            if not isinstance(msg, dict):
                continue
            role = msg.get("role", "?")
            role_label = {
                "user": tr("用户"),
                "assistant": "AI",
                "system": tr("系统"),
                "tool": tr("工具"),
            }.get(role, role)
            content = msg.get("content", [])

            # --- 角色过滤 ---
            if role == "user" and not self.show_user.get():
                continue
            if role == "assistant" and not self.show_assistant.get():
                continue
            if role == "tool" and not self.show_tool.get():
                continue

            # 提取文本
            text = extract_message_text(msg)

            # 检测纯思考
            has_only_think = False
            if isinstance(content, list) and len(content) > 0:
                types = {b.get("type") for b in content if isinstance(b, dict)}
                if types == {"think"}:
                    has_only_think = True

            # 预览文本
            if text:
                preview = truncate(text, 80)
            elif has_only_think:
                preview = "(思考中)"
            else:
                preview = "(空)"

            # 类型标签
            type_tags = []
            if has_only_think or (
                isinstance(content, list)
                and any(b.get("type") == "think" for b in content if isinstance(b, dict))
            ):
                type_tags.append(tr("含思考"))
            tc = msg.get("tool_calls", [])
            if tc:
                names = [t.get("function", {}).get("name", "?") for t in tc]
                type_tags.append("调用: " + ",".join(names))
            type_label = " | ".join(type_tags) if type_tags else ""

            # 默认全部勾选
            self.selected_indices.add(i)
            check_mark = "☑"

            # 颜色标签：用户=灰, AI=默认, 工具=蓝
            tags = []
            if role == "user":
                tags.append("role_user")
            elif role == "tool":
                tags.append("role_tool")
            if "<system_reminder>" in text:
                tags.append("system_reminder")

            self.msg_tree.insert(
                "",
                tk.END,
                iid=str(i),
                values=(check_mark, i + 1, role_label, preview, type_label),
                tags=tuple(tags) if tags else (),
            )

        self._update_selection_count()

    def _update_selection_count(self):
        """更新选择计数。真实勾选数永远基于原始数组，过滤只影响显示。"""
        visible = len(self.msg_tree.get_children())
        real_total = self._total_msg_count
        real_selected = len(self.selected_indices)

        self.selection_count_var.set(
            tr(
                "已勾选 {}/{} 条（显示 {} 条）",
                real_selected,
                real_total,
                visible,
            )
        )
        if visible != real_total:
            self.import_count_var.set(
                tr(
                    "全部 {} 条消息 | 已勾选 {} 条 | 当前显示 {} 条",
                    real_total,
                    real_selected,
                    visible,
                )
            )
        else:
            self.import_count_var.set(
                tr(
                    "共 {} 条消息 | 已勾选 {} 条",
                    real_total,
                    real_selected,
                )
            )

    def _on_checkbox_click(self, event):
        """处理复选框列的点击切换"""
        column = self.msg_tree.identify_column(event.x)
        if column != "#1":  # check 列
            return
        item = self.msg_tree.identify_row(event.y)
        if not item:
            return
        idx = int(item)
        if idx in self.selected_indices:
            self.selected_indices.discard(idx)
            self.msg_tree.set(item, "check", "☐")
        else:
            self.selected_indices.add(idx)
            self.msg_tree.set(item, "check", "☑")
        self._update_selection_count()

    def _select_all(self):
        for item in self.msg_tree.get_children():
            idx = int(item)
            self.selected_indices.add(idx)
            self.msg_tree.set(item, "check", "☑")
        self._update_selection_count()

    def _deselect_all(self):
        for item in self.msg_tree.get_children():
            idx = int(item)
            self.selected_indices.discard(idx)
            self.msg_tree.set(item, "check", "☐")
        self._update_selection_count()

    def _invert_selection(self):
        for item in self.msg_tree.get_children():
            idx = int(item)
            if idx in self.selected_indices:
                self.selected_indices.discard(idx)
                self.msg_tree.set(item, "check", "☐")
            else:
                self.selected_indices.add(idx)
                self.msg_tree.set(item, "check", "☑")
        self._update_selection_count()

    def _select_by_role(self, role: str):
        """选中或取消选中指定角色的所有可见消息"""
        # 获取当前所有可见行
        visible_indices = []
        for item in self.msg_tree.get_children():
            values = self.msg_tree.item(item, "values")
            if values and len(values) >= 3:
                role_label = values[2]
                role_map = {
                    tr("用户"): "user",
                    "AI": "assistant",
                    tr("工具"): "tool",
                }
                if role_map.get(role_label) == role:
                    visible_indices.append(int(item))

        if not visible_indices:
            return

        # 检查是否已经全部选中 → 则取消；否则选中
        all_selected = all(idx in self.selected_indices for idx in visible_indices)

        for idx in visible_indices:
            item = str(idx)
            if all_selected:
                self.selected_indices.discard(idx)
                self.msg_tree.set(item, "check", "☐")
            else:
                self.selected_indices.add(idx)
                self.msg_tree.set(item, "check", "☑")

        self._update_selection_count()

    def _check_selected(self):
        """勾选所有高亮（Shift/Ctrl选中）的行"""
        for item in self.msg_tree.selection():
            idx = int(item)
            self.selected_indices.add(idx)
            self.msg_tree.set(item, "check", "☑")
        self._update_selection_count()

    def _uncheck_selected(self):
        """取消勾选所有高亮（Shift/Ctrl选中）的行"""
        for item in self.msg_tree.selection():
            idx = int(item)
            self.selected_indices.discard(idx)
            self.msg_tree.set(item, "check", "☐")
        self._update_selection_count()

    # ---- 导入 ----

    def _do_import(self):
        if self.db is None:
            messagebox.showwarning(tr("提示"), tr("请先在主窗口点击「打开数据库」选择数据库文件"))
            return
        if not self.conversations:
            messagebox.showwarning(tr("提示"), tr("请先加载导出文件"))
            return

        selection = self.conv_listbox.curselection()
        if not selection:
            messagebox.showwarning(tr("提示"), tr("请先在左侧选择一个对话"))
            return
        conv_idx = selection[0]
        conv = self.conversations[conv_idx]

        cid = conv["conversation_id"]
        all_messages = conv.get("content", [])
        if not isinstance(all_messages, list):
            all_messages = []

        # 筛选勾选的消息（保持原始顺序）
        selected = [
            all_messages[i]
            for i in sorted(self.selected_indices)
            if i < len(all_messages)
        ]

        if not selected:
            messagebox.showwarning(tr("提示"), tr("没有勾选任何消息"))
            return

        # 检查冲突
        if self.db.conversation_exists(cid):
            existing = self.db.get_conversation(cid)
            exist_count = existing["message_count"] if existing else 0

            # 自定义三按钮对话框
            choice_dialog = tk.Toplevel(self)
            choice_dialog.title(tr("对话已存在"))
            choice_dialog.geometry("480x260")
            choice_dialog.resizable(False, False)
            choice_dialog.transient(self)
            center_window(choice_dialog, self)

            ttk.Label(
                choice_dialog,
                text=tr("对话 {}...\n数据库中已有 {} 条消息，你选中了 {} 条。", cid[:24], exist_count, len(selected)),
                wraplength=440,
                justify=tk.CENTER,
            ).pack(padx=20, pady=(20, 15))

            result = {"action": None}

            def do(action_name):
                result["action"] = action_name
                choice_dialog.destroy()

            btn_frame = ttk.Frame(choice_dialog)
            btn_frame.pack(pady=5)
            ttk.Button(
                btn_frame, text=tr("覆盖（替换为 {} 条）", len(selected)),
                command=lambda: do("overwrite")
            ).pack(fill=tk.X, padx=20, pady=3)
            ttk.Button(
                btn_frame, text=tr("合并·去重（跳过完全相同的消息）"),
                command=lambda: do("merge_dedup")
            ).pack(fill=tk.X, padx=20, pady=3)
            ttk.Button(
                btn_frame, text=tr("强制追加（保留重复）"),
                command=lambda: do("merge_force")
            ).pack(fill=tk.X, padx=20, pady=3)
            ttk.Button(
                btn_frame, text=tr("取消（不导入）"),
                command=lambda: do("cancel")
            ).pack(fill=tk.X, padx=20, pady=3)

            choice_dialog.grab_set()
            self.wait_window(choice_dialog)

            action = result["action"]
            if action == "cancel" or action is None:
                return
            elif action == "merge_dedup":
                added = self.db.merge_conversation(cid, selected, dedup=True)
                skipped = len(selected) - added
                msg = tr("已合并 {} 条消息到 {}", added, cid)
                if skipped > 0:
                    msg += tr("（跳过 {} 条重复）", skipped)
                self.status_var.set(msg)
                if self.on_imported:
                    self.on_imported()
                messagebox.showinfo(tr("完成"), msg)
                return
            elif action == "merge_force":
                added = self.db.merge_conversation(cid, selected, dedup=False)
                self.status_var.set(tr("已强制追加 {} 条消息到 {}", added, cid))
                if self.on_imported:
                    self.on_imported()
                messagebox.showinfo(tr("完成"), tr("已追加强制 {} 条消息", added))
                return
            # action == "overwrite": fall through to replace logic below

        # 准备导入数据
        import_conv = {
            "conversation_id": cid,
            "user_id": conv["user_id"],
            "platform_id": conv.get("platform_id", "default"),
            "content": selected,
            "title": conv.get("title"),
            "persona_id": conv.get("persona_id"),
            "created_at": conv.get("created_at"),
            "updated_at": conv.get("updated_at"),
        }

        try:
            if self.db.conversation_exists(cid):
                self.db.update_content(cid, selected)
            else:
                self.db.insert_conversation(import_conv)
            self.status_var.set(
                tr(
                    "导入成功: {}/{} 条消息 → {}",
                    len(selected),
                    len(all_messages),
                    cid,
                )
            )
            if self.on_imported:
                self.on_imported()
            messagebox.showinfo(tr("完成"), tr("成功导入 {} 条消息", len(selected)))
        except Exception as e:
            messagebox.showerror(tr("导入失败"), translate_text(str(e)))


# ============================================================
# GUI: 数据管理标签页
# ============================================================


class ManageTab(ttk.Frame):
    """数据管理标签页"""

    def __init__(self, parent, db: ConversationDB):
        super().__init__(parent)
        self.db = db
        self.conversations = []
        self.current_conv = None  # 当前选中的对话

        # 角色过滤状态（默认全部显示）
        self.show_user = tk.BooleanVar(value=True)
        self.show_assistant = tk.BooleanVar(value=True)
        self.show_tool = tk.BooleanVar(value=True)

        self._build_ui()
        self._refresh()

    def update_db(self, db: ConversationDB):
        """切换数据库引用并刷新"""
        self.db = db
        self._clear_messages()
        self._refresh()

    def retranslate(self):
        self._refresh()
        self.status_info("数据库已切换")

    def _build_ui(self):
        # === 顶栏：搜索 ===
        top_frame = ttk.Frame(self)
        top_frame.pack(fill=tk.X, padx=10, pady=10)

        ttk.Label(top_frame, text="搜索:").pack(side=tk.LEFT)
        self.search_var = tk.StringVar()
        search_entry = ttk.Entry(top_frame, textvariable=self.search_var, width=30)
        search_entry.pack(side=tk.LEFT, padx=5)
        search_entry.bind("<Return>", lambda e: self._refresh())
        ttk.Button(top_frame, text="搜索", command=self._refresh).pack(side=tk.LEFT, padx=2)
        ttk.Button(top_frame, text="刷新", command=self._refresh).pack(side=tk.LEFT)
        ttk.Button(top_frame, text="清空搜索", command=self._clear_search).pack(
            side=tk.LEFT, padx=2
        )

        # === 对话列表（上部） ===
        conv_frame = ttk.LabelFrame(self, text="数据库对话列表")
        conv_frame.pack(fill=tk.BOTH, expand=False, padx=10, pady=5)

        columns = ("cid", "user_id", "platform", "count", "created", "updated")
        self.conv_tree = ttk.Treeview(
            conv_frame,
            columns=columns,
            show="headings",
            selectmode="browse",
            height=8,
        )
        self.conv_tree.heading("cid", text="对话 ID")
        self.conv_tree.heading("user_id", text="用户")
        self.conv_tree.heading("platform", text="平台")
        self.conv_tree.heading("count", text="消息数")
        self.conv_tree.heading("created", text="创建时间")
        self.conv_tree.heading("updated", text="更新时间")

        self.conv_tree.column("cid", width=260, anchor=tk.CENTER, stretch=True)
        self.conv_tree.column("user_id", width=130, anchor=tk.CENTER, stretch=True)
        self.conv_tree.column("platform", width=65, anchor=tk.CENTER, stretch=False)
        self.conv_tree.column("count", width=50, anchor=tk.CENTER, stretch=False)
        self.conv_tree.column("created", width=145, anchor=tk.CENTER, stretch=False)
        self.conv_tree.column("updated", width=145, anchor=tk.CENTER, stretch=False)

        self.conv_tree.bind("<<TreeviewSelect>>", self._on_conv_select)
        self.conv_tree.bind("<Button-3>", self._on_conv_right_click)  # 右键

        conv_scroll_y = ttk.Scrollbar(conv_frame, command=self.conv_tree.yview)
        conv_scroll_x = ttk.Scrollbar(conv_frame, orient=tk.HORIZONTAL, command=self.conv_tree.xview)
        self.conv_tree.configure(yscrollcommand=conv_scroll_y.set, xscrollcommand=conv_scroll_x.set)

        self.conv_tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=5, pady=(5, 0))
        conv_scroll_y.pack(side=tk.RIGHT, fill=tk.Y, pady=(5, 0))
        conv_scroll_x.pack(side=tk.BOTTOM, fill=tk.X, padx=5)

        # 对话右键菜单
        self.conv_menu = tk.Menu(self, tearoff=0)
        self.conv_menu.add_command(label="复制对话 ID", command=self._copy_conv_id)
        self.conv_menu.add_command(label="修改对话 ID", command=self._rename_conv_id)
        self.conv_menu.add_separator()
        self.conv_menu.add_command(label="删除整个对话", command=self._delete_current_conv)

        # === 消息列表（下部） ===
        msg_frame = ttk.LabelFrame(self, text="消息内容")
        msg_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=5)

        # 消息工具栏
        msg_toolbar = ttk.Frame(msg_frame)
        msg_toolbar.pack(fill=tk.X, padx=5, pady=(5, 0))

        ttk.Label(msg_toolbar, text="操作:").pack(side=tk.LEFT)
        ttk.Button(
            msg_toolbar, text="编辑消息", command=self._edit_selected_message
        ).pack(side=tk.LEFT, padx=2)
        ttk.Button(
            msg_toolbar, text="删除消息", command=self._delete_selected_messages
        ).pack(side=tk.LEFT, padx=2)
        ttk.Button(
            msg_toolbar, text="添加消息", command=self._add_message
        ).pack(side=tk.LEFT, padx=2)
        ttk.Button(
            msg_toolbar, text="展开", command=self._expand_all
        ).pack(side=tk.LEFT, padx=2)
        ttk.Button(
            msg_toolbar, text="收起", command=self._collapse_all
        ).pack(side=tk.LEFT, padx=2)

        ttk.Separator(msg_toolbar, orient=tk.VERTICAL).pack(
            side=tk.LEFT, fill=tk.Y, padx=8, pady=1
        )

        ttk.Label(msg_toolbar, text="显示:").pack(side=tk.LEFT)
        ttk.Checkbutton(
            msg_toolbar, text="用户", variable=self.show_user, command=self._apply_filter
        ).pack(side=tk.LEFT, padx=3)
        ttk.Checkbutton(
            msg_toolbar, text="AI", variable=self.show_assistant, command=self._apply_filter
        ).pack(side=tk.LEFT, padx=3)
        ttk.Checkbutton(
            msg_toolbar, text="工具", variable=self.show_tool, command=self._apply_filter
        ).pack(side=tk.LEFT, padx=3)

        # 消息树 + 预览区（垂直分割）
        msg_paned = ttk.PanedWindow(msg_frame, orient=tk.VERTICAL)
        msg_paned.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)

        # 消息 Treeview（上部）
        tree_frame = ttk.Frame(msg_paned)
        msg_paned.add(tree_frame, weight=3)

        m_columns = ("m_index", "m_role", "m_content", "m_type")
        self.msg_tree = ttk.Treeview(
            tree_frame,
            columns=m_columns,
            show="headings",
            selectmode="extended",
            height=12,
        )
        self.msg_tree.heading("m_index", text="#")
        self.msg_tree.heading("m_role", text="角色")
        self.msg_tree.heading("m_content", text="内容")
        self.msg_tree.heading("m_type", text="类型")

        self.msg_tree.column("m_index", width=40, anchor=tk.CENTER, stretch=False)
        self.msg_tree.column("m_role", width=55, anchor=tk.CENTER, stretch=False)
        self.msg_tree.column("m_content", width=400)
        self.msg_tree.column("m_type", width=250, anchor=tk.CENTER, stretch=False)

        self.msg_tree.bind("<Double-1>", self._on_message_double_click)
        self.msg_tree.bind("<Button-3>", self._on_msg_right_click)
        self.msg_tree.bind("<<TreeviewSelect>>", self._on_msg_select)

        tree_scroll_y = ttk.Scrollbar(tree_frame, command=self.msg_tree.yview)
        tree_scroll_x = ttk.Scrollbar(tree_frame, orient=tk.HORIZONTAL, command=self.msg_tree.xview)
        self.msg_tree.configure(yscrollcommand=tree_scroll_y.set, xscrollcommand=tree_scroll_x.set)

        self.msg_tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        tree_scroll_y.pack(side=tk.RIGHT, fill=tk.Y)
        tree_scroll_x.pack(side=tk.BOTTOM, fill=tk.X)

        # 颜色标签
        self.msg_tree.tag_configure("role_user", foreground="gray")
        self.msg_tree.tag_configure("role_tool", foreground="#0066CC")

        # 预览区（下部）
        preview_frame = ttk.LabelFrame(msg_paned, text="消息预览")
        msg_paned.add(preview_frame, weight=1)

        self.preview_text = tk.Text(
            preview_frame,
            wrap=tk.WORD,
            font=("Microsoft YaHei", 10),
            state=tk.DISABLED,
            height=5,
        )
        preview_scroll = ttk.Scrollbar(preview_frame, command=self.preview_text.yview)
        self.preview_text.configure(yscrollcommand=preview_scroll.set)

        self.preview_text.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=5, pady=5)
        preview_scroll.pack(side=tk.RIGHT, fill=tk.Y, pady=5)

        # 右键菜单
        self.msg_menu = tk.Menu(self, tearoff=0)
        self.msg_menu.add_command(label="编辑此消息", command=self._edit_selected_message)
        self.msg_menu.add_command(
            label="删除选中消息", command=self._delete_selected_messages
        )
        self.msg_menu.add_separator()
        self.msg_menu.add_command(label="在此位置前插入", command=self._add_message)
        self.msg_menu.add_command(label="在此位置后插入", command=self._add_message_after)

    # ---- 刷新 ----

    def _refresh(self):
        if self.db is None:
            self.status_info("请先打开数据库文件")
            return
        search = self.search_var.get().strip()
        self.conversations = self.db.list_conversations(search)
        self._populate_conv_list()
        if self.conversations:
            first_id = self.conversations[0]["conversation_id"]
            self.conv_tree.selection_set(first_id)
            self.conv_tree.focus(first_id)
            self._on_conv_select(None)
        else:
            self._clear_messages()

    def _clear_search(self):
        self.search_var.set("")
        self._refresh()

    def _populate_conv_list(self):
        self.conv_tree.delete(*self.conv_tree.get_children())
        for conv in self.conversations:
            cid_full = conv["conversation_id"]
            user_label = ImportManager.format_user_id(conv.get("user_id", "?"))
            platform = conv.get("platform_id", "-")
            count = conv.get("message_count", 0)
            created = timestamp_to_display(conv.get("created_at"))
            updated = timestamp_to_display(conv.get("updated_at"))
            self.conv_tree.insert(
                "",
                tk.END,
                iid=conv["conversation_id"],
                values=(cid_full, user_label, platform, count, created, updated),
            )

    def _clear_messages(self):
        self.msg_tree.delete(*self.msg_tree.get_children())
        self._clear_preview()
        self.current_conv = None

    def _clear_preview(self):
        self.preview_text.configure(state=tk.NORMAL)
        self.preview_text.delete("1.0", tk.END)
        self.preview_text.configure(state=tk.DISABLED)

    # ---- 对话选择 ----

    def _on_conv_select(self, event):
        selection = self.conv_tree.selection()
        if not selection:
            self._clear_messages()
            return
        cid = selection[0]
        # 找到完整对话数据
        conv = None
        for c in self.conversations:
            if c["conversation_id"] == cid:
                conv = c
                break
        if conv is None:
            conv = self.db.get_conversation(cid)
            if conv is None:
                return
        self.current_conv = conv
        self._show_messages(conv)

    def _on_conv_right_click(self, event):
        """对话列表右键"""
        item = self.conv_tree.identify_row(event.y)
        if item:
            self.conv_tree.selection_set(item)
            self._on_conv_select(None)
            self.conv_menu.post(event.x_root, event.y_root)

    # ---- 消息显示 ----

    def _show_messages(self, conv: dict):
        """显示对话的消息，每个 content block 独立一行。受角色过滤复选框控制。"""
        self.msg_tree.delete(*self.msg_tree.get_children())
        messages = conv.get("_messages", [])
        if not isinstance(messages, list):
            return

        for i, msg in enumerate(messages):
            if not isinstance(msg, dict):
                continue

            role = msg.get("role", "?")
            role_label = {
                "user": tr("用户"),
                "assistant": "AI",
                "system": tr("系统"),
                "tool": tr("工具"),
            }.get(role, role)
            content = msg.get("content", [])

            # --- 角色过滤 ---
            if role == "user" and not self.show_user.get():
                continue
            if role == "assistant" and not self.show_assistant.get():
                continue
            if role == "tool" and not self.show_tool.get():
                continue
            # 放行 system 等不常见角色

            # 提取 tool_calls 名称（assistant 消息的顶层字段）
            tool_calls = msg.get("tool_calls", [])
            tc_names = []
            if tool_calls:
                for tc in tool_calls:
                    fn = tc.get("function", {})
                    tc_names.append(fn.get("name", "?"))

            # --- 计算通用值 ---
            text_summary = extract_message_text(msg)

            # 检测是否只有思考块（无可见文本）
            has_only_think = False
            if isinstance(content, list) and len(content) > 0:
                types = {b.get("type") for b in content if isinstance(b, dict)}
                if types == {"think"}:
                    has_only_think = True

            # 构建类型标签
            type_tags = []
            if has_only_think or (
                isinstance(content, list)
                and any(b.get("type") == "think" for b in content if isinstance(b, dict))
            ):
                type_tags.append("含思考")
            if tc_names:
                type_tags.append(tr("调用: ") + ", ".join(tc_names))
            type_label = " | ".join(type_tags) if type_tags else ""

            # 显示文本
            if text_summary:
                display_text = truncate(text_summary, 80)
            elif has_only_think:
                display_text = tr("(思考中)")
            else:
                display_text = tr("(空)")

            # --- 颜色标签 ---
            tags = []
            if role == "user":
                tags.append("role_user")
            elif role == "tool":
                tags.append("role_tool")

            # --- 插入父节点 ---
            msg_iid = f"msg_{i}"
            self.msg_tree.insert(
                "",
                tk.END,
                iid=msg_iid,
                values=(i + 1, role_label, display_text, type_label),
                tags=tuple(tags) if tags else (),
                open=False,
            )

            # --- 插入子节点（content blocks） ---
            if isinstance(content, str):
                # tool 消息：content 是纯字符串
                self.msg_tree.insert(
                    msg_iid,
                    tk.END,
                    iid=f"msg_{i}_block_0",
                    values=("", "", truncate(content, 200), tr("工具输出")),
                )
            elif isinstance(content, list):
                for j, block in enumerate(content):
                    if not isinstance(block, dict):
                        continue
                    block_type = block.get("type", "?")
                    if block_type == "text":
                        block_text = block.get("text", "")
                    elif block_type == "think":
                        block_text = truncate(block.get("think", ""), 120)
                    else:
                        block_text = truncate(str(block), 60)

                    self.msg_tree.insert(
                        msg_iid,
                        tk.END,
                        iid=f"msg_{i}_block_{j}",
                        values=("", "", block_text, block_type),
                    )

    def _expand_all(self):
        """展开所有消息节点"""
        for item in self.msg_tree.get_children():
            self.msg_tree.item(item, open=True)

    def _collapse_all(self):
        """收起所有消息节点"""
        for item in self.msg_tree.get_children():
            self.msg_tree.item(item, open=False)

    def _apply_filter(self):
        """角色过滤复选框变化时重新显示消息"""
        if self.current_conv:
            self._show_messages(self.current_conv)

    # ---- 消息操作 ----

    def _get_selected_message_indices(self) -> list[int]:
        """获取选中消息的索引列表"""
        indices = set()
        for item in self.msg_tree.selection():
            # 解析 item iid
            if item.startswith("msg_"):
                parts = item.split("_")
                if len(parts) >= 2:
                    try:
                        indices.add(int(parts[1]))
                    except ValueError:
                        pass
        return sorted(indices)

    def _on_message_double_click(self, event):
        self._edit_selected_message()
        return "break"  # 阻止默认的展开/收起行为

    def _on_msg_right_click(self, event):
        """消息右键菜单"""
        item = self.msg_tree.identify_row(event.y)
        if item:
            self.msg_tree.selection_set(item)
            self.msg_menu.post(event.x_root, event.y_root)

    def _on_msg_select(self, event):
        """选中消息时在预览区显示完整内容"""
        selection = self.msg_tree.selection()
        if not selection or not self.current_conv:
            self._clear_preview()
            return
        # 取第一个选中项
        item = selection[0]
        # 解析消息索引
        if not item.startswith("msg_"):
            return
        parts = item.split("_")
        if len(parts) < 2:
            return
        try:
            idx = int(parts[1])
        except ValueError:
            return

        messages = self.current_conv.get("_messages", [])
        if idx >= len(messages):
            return
        msg = messages[idx]

        # 判断选中项是父节点还是子 block
        if item.count("_") == 1:
            # 父节点（消息本身）— 显示完整消息
            text = extract_message_text(msg)
            role = msg.get("role", "?")
            role_label = {
                "user": tr("用户"),
                "assistant": "AI",
                "system": tr("系统"),
                "tool": tr("工具"),
            }.get(role, role)

            if not text:
                # 可能是纯思考
                content = msg.get("content", [])
                if isinstance(content, list):
                    for b in content:
                        if isinstance(b, dict) and b.get("type") == "think":
                            text = b.get("think", "")
                            break
                if not text and isinstance(content, str):
                    text = content

            header = f"[{role_label}] 消息 #{idx + 1}\n{'─' * 40}\n"
        else:
            # 子节点（content block）— 显示该 block 的内容
            block_idx = int(parts[3]) if len(parts) > 3 else 0
            content = msg.get("content", [])
            if isinstance(content, list) and block_idx < len(content):
                block = content[block_idx]
                block_type = block.get("type", "?")
                if block_type == "text":
                    text = block.get("text", "")
                elif block_type == "think":
                    text = block.get("think", "")
                else:
                    text = json.dumps(block, ensure_ascii=False, indent=2)
                header = f"[{block_type}] 消息 #{idx + 1} 内容块 #{block_idx + 1}\n{'─' * 40}\n"
            elif isinstance(content, str):
                text = content
                header = f"[工具输出] 消息 #{idx + 1}\n{'─' * 40}\n"
            else:
                text = str(content)
                header = f"[原始] 消息 #{idx + 1}\n{'─' * 40}\n"

        self.preview_text.configure(state=tk.NORMAL)
        self.preview_text.delete("1.0", tk.END)
        self.preview_text.insert("1.0", header + text)
        self.preview_text.configure(state=tk.DISABLED)

    def _edit_selected_message(self):
        if not self.current_conv:
            return
        indices = self._get_selected_message_indices()
        if not indices:
            messagebox.showwarning(tr("提示"), tr("请先选中一条消息"))
            return
        # 编辑第一条选中的
        idx = indices[0]
        messages = self.current_conv.get("_messages", [])
        if idx >= len(messages):
            return

        dialog = MessageEditDialog(self, messages[idx], idx)
        self.wait_window(dialog)

        result = dialog.result
        if result is not None:
            cid = self.current_conv["conversation_id"]
            try:
                self.db.update_message_at(cid, idx, result)
                self._refresh_current_conv()
            except Exception as e:
                messagebox.showerror(tr("保存失败"), translate_text(str(e)))
        # 即使 result 为 None（用户取消），也不报错

    def _delete_selected_messages(self):
        if not self.current_conv:
            return
        indices = self._get_selected_message_indices()
        if not indices:
            messagebox.showwarning(tr("提示"), tr("请先选中要删除的消息"))
            return

        if not messagebox.askyesno(
            tr("确认删除"),
            tr(
                "确定要删除 {} 条选中的消息吗？\n此操作不可撤销。",
                len(indices),
            ),
        ):
            return

        cid = self.current_conv["conversation_id"]
        try:
            # 从后往前删，保持索引正确
            for idx in reversed(indices):
                self.db.delete_message_at(cid, idx)
            self._refresh_current_conv()
            self.status_info(tr("已删除 {} 条消息", len(indices)))
        except Exception as e:
            messagebox.showerror(tr("删除失败"), translate_text(str(e)))

    def _add_message(self):
        """在选中位置前插入新消息"""
        if not self.current_conv:
            messagebox.showwarning(tr("提示"), tr("请先选择一个对话"))
            return
        indices = self._get_selected_message_indices()
        insert_at = indices[0] if indices else len(
            self.current_conv.get("_messages", [])
        )
        self._insert_new_message(insert_at)

    def _add_message_after(self):
        """在选中位置后插入新消息"""
        if not self.current_conv:
            messagebox.showwarning(tr("提示"), tr("请先选择一个对话"))
            return
        indices = self._get_selected_message_indices()
        insert_at = (
            indices[-1] + 1
            if indices
            else len(self.current_conv.get("_messages", []))
        )
        self._insert_new_message(insert_at)

    def _insert_new_message(self, index: int):
        """弹出编辑框，在指定位置插入新消息"""
        empty_msg = {"role": "user", "content": [{"type": "text", "text": ""}]}
        dialog = MessageEditDialog(self, empty_msg, -1)
        dialog.title(f"添加新消息 (插入位置: {index + 1})")
        self.wait_window(dialog)

        if dialog.result is not None:
            cid = self.current_conv["conversation_id"]
            try:
                self.db.insert_message_at(cid, index, dialog.result)
                self._refresh_current_conv()
                self.status_info(tr("新消息已插入到位置 #{}", index + 1))
            except Exception as e:
                messagebox.showerror(tr("添加失败"), translate_text(str(e)))

    def _copy_conv_id(self):
        """复制对话 ID 到剪贴板"""
        if not self.current_conv:
            return
        cid = self.current_conv["conversation_id"]
        self.clipboard_clear()
        self.clipboard_append(cid)
        self.status_info(tr("已复制: {}", cid))

    def _rename_conv_id(self):
        """修改当前对话的 ID"""
        if not self.current_conv:
            return
        old_id = self.current_conv["conversation_id"]

        dialog = tk.Toplevel(self)
        dialog.title(tr("修改对话 ID"))
        dialog.geometry("500x150")
        dialog.resizable(False, False)
        dialog.transient(self)
        center_window(dialog, self)

        ttk.Label(
            dialog, text=tr("当前 ID: {}", old_id),
            wraplength=460,
        ).pack(padx=20, pady=(15, 5))

        ttk.Label(dialog, text=tr("新 ID:")).pack(anchor=tk.W, padx=20)
        new_id_var = tk.StringVar(value=old_id)
        entry = ttk.Entry(dialog, textvariable=new_id_var, width=55)
        entry.pack(padx=20, pady=5)
        entry.select_range(0, tk.END)
        entry.focus_set()

        def do_rename():
            new_id = new_id_var.get().strip()
            if not new_id:
                messagebox.showwarning(tr("提示"), tr("ID 不能为空"), parent=dialog)
                return
            if new_id == old_id:
                dialog.destroy()
                return
            try:
                self.db.update_conversation_id(old_id, new_id)
                self.status_info(
                    tr("ID 已更新: {}... → {}...", old_id[:12], new_id[:12])
                )
                dialog.destroy()
                self._refresh()
            except Exception as e:
                messagebox.showerror(tr("修改失败"), translate_text(str(e)), parent=dialog)

        btn_frame = ttk.Frame(dialog)
        btn_frame.pack(pady=10)
        ttk.Button(btn_frame, text=tr("确定"), command=do_rename).pack(side=tk.LEFT, padx=5)
        ttk.Button(btn_frame, text=tr("取消"), command=dialog.destroy).pack(side=tk.LEFT)

        dialog.grab_set()
        self.wait_window(dialog)

    def _delete_current_conv(self):
        if not self.current_conv:
            return
        cid = self.current_conv["conversation_id"]
        count = self.current_conv.get("message_count", 0)
        if not messagebox.askyesno(
            tr("确认删除"),
            tr(
                "确定要删除整个对话吗？\n\n对话 ID: {}...\n消息数: {}\n\n此操作不可撤销。",
                cid[:16],
                count,
            ),
        ):
            return
        try:
            self.db.delete_conversation(cid)
            self._refresh()
            self.status_info(tr("对话 {}... 已删除", cid[:8]))
        except Exception as e:
            messagebox.showerror("删除失败", str(e))

    def _refresh_current_conv(self):
        """刷新当前选中对话的显示（保留选中和消息视图）"""
        if not self.current_conv:
            return
        cid = self.current_conv["conversation_id"]
        # 重新从 DB 加载当前对话
        self.current_conv = self.db.get_conversation(cid)
        # 重新加载对话列表（仅更新计数等，不清空消息）
        search = self.search_var.get().strip()
        self.conversations = self.db.list_conversations(search)
        self._populate_conv_list()
        # 恢复对话选中状态
        if cid in self.conv_tree.get_children():
            self.conv_tree.selection_set(cid)
        # 显示消息
        if self.current_conv:
            self._show_messages(self.current_conv)

    def status_info(self, msg: str):
        """将状态消息传递给主窗口"""
        # 向上查找 MainWindow
        parent = self.master
        while parent is not None:
            if hasattr(parent, "set_status"):
                parent.set_status(msg)
                return
            parent = parent.master


# ============================================================
# GUI: 主窗口
# ============================================================


class DatabasePickerDialog(tk.Toplevel):
    """Modal chooser used when more than one database is detected."""

    def __init__(self, parent, candidates, path_formatter):
        super().__init__(parent)
        self.result = None
        self._candidates = list(candidates)
        self._path_formatter = path_formatter

        self.title(tr("选择 AstrBot 数据库"))
        self.geometry("760x340")
        self.minsize(620, 260)
        self.transient(parent)
        self.grab_set()

        frame = ttk.Frame(self, padding=12)
        frame.pack(fill=tk.BOTH, expand=True)

        ttk.Label(
            frame,
            text=tr("检测到多个 AstrBot 数据库，请选择要编辑的一个："),
            font=("Microsoft YaHei", 10),
        ).pack(anchor=tk.W, pady=(0, 8))

        tree_frame = ttk.Frame(frame)
        tree_frame.pack(fill=tk.BOTH, expand=True)

        self.tree = ttk.Treeview(
            tree_frame,
            columns=("kind", "path"),
            show="headings",
            selectmode="browse",
        )
        self.tree.heading("kind", text=tr("来源"))
        self.tree.heading("path", text=tr("路径"))
        self.tree.column("kind", width=190, stretch=False)
        self.tree.column("path", width=500, stretch=True)

        scrollbar = ttk.Scrollbar(
            tree_frame, orient=tk.VERTICAL, command=self.tree.yview
        )
        self.tree.configure(yscrollcommand=scrollbar.set)
        self.tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)

        for index, candidate in enumerate(self._candidates):
            self.tree.insert(
                "",
                tk.END,
                iid=str(index),
                values=(
                    translate_text(candidate.display_name),
                    path_formatter(candidate.path),
                ),
            )
        if self._candidates:
            self.tree.selection_set("0")
            self.tree.focus("0")

        buttons = ttk.Frame(frame)
        buttons.pack(fill=tk.X, pady=(10, 0))
        ttk.Button(buttons, text=tr("取消"), command=self._cancel).pack(side=tk.RIGHT)
        ttk.Button(buttons, text=tr("打开"), command=self._accept).pack(
            side=tk.RIGHT, padx=(0, 6)
        )

        self.bind("<Return>", lambda event: self._accept())
        self.bind("<Escape>", lambda event: self._cancel())
        self.tree.bind("<Double-1>", lambda event: self._accept())
        self.protocol("WM_DELETE_WINDOW", self._cancel)

        apply_language(self)
        center_window(self, parent)
        self.wait_window(self)

    def _accept(self):
        selection = self.tree.selection()
        if not selection:
            return
        index = int(selection[0])
        if 0 <= index < len(self._candidates):
            self.result = self._candidates[index]
        self.destroy()

    def _cancel(self):
        self.result = None
        self.destroy()


class MainWindow(tk.Tk):
    """Main application window."""

    def __init__(
        self,
        db_path: str | None = None,
        initial_tab: str = "manage",
        import_file: str | None = None,
    ):
        set_language(load_language())
        super().__init__()

        self.title(tr("AstrBot 对话数据管理工具 {}", __version__))
        self.geometry("1100x750")
        self.minsize(900, 600)
        self.update_idletasks()
        left, top, right, bottom = get_work_area(self)
        width = self.winfo_width()
        height = self.winfo_height()
        self.geometry(
            f"+{left + (right - left - width) // 2}"
            f"+{top + (bottom - top - height) // 2}"
        )

        # Center the complete window frame (title bar included), not only the
        # client area.  On Windows Tk's geometry coordinates refer to the
        # frame, so measuring the frame avoids a small vertical offset.
        try:
            hwnd = self.winfo_id()
            frame = ctypes.windll.user32.GetParent(hwnd)
            rect = wintypes.RECT()
            if frame and ctypes.windll.user32.GetWindowRect(
                frame, ctypes.byref(rect)
            ):
                frame_width = rect.right - rect.left
                frame_height = rect.bottom - rect.top
                self.geometry(
                    f"+{left + (right - left - frame_width) // 2}"
                    f"+{top + (bottom - top - frame_height) // 2}"
                )
        except Exception:
            pass

        self.db_path = ""
        self.db = None
        self._db_candidate = None
        self._candidates = detect_databases()
        self._wal_warned = False

        header = ttk.Frame(self)
        header.pack(fill=tk.X, padx=10, pady=(10, 0))

        title_row = ttk.Frame(header)
        title_row.pack(fill=tk.X)

        ttk.Label(
            title_row,
            text="AstrBot 对话数据管理",
            font=("Microsoft YaHei", 14, "bold"),
        ).pack(side=tk.LEFT)

        ttk.Button(
            title_row,
            text="打开数据库",
            command=self._open_database,
        ).pack(side=tk.RIGHT)
        ttk.Button(
            title_row,
            text="自动检测",
            command=self._detect_and_choose,
        ).pack(side=tk.RIGHT, padx=(0, 6))

        self.language_var = tk.StringVar(
            value="简体中文" if i18n.current == "zh" else "English"
        )
        self.language_box = ttk.Combobox(
            title_row,
            textvariable=self.language_var,
            values=("简体中文", "English"),
            width=10,
            state="readonly",
        )
        self.language_box.pack(side=tk.RIGHT, padx=(0, 6))
        self.language_box.bind(
            "<<ComboboxSelected>>", self._on_language_changed
        )

        self.db_label_var = tk.StringVar(value="数据库：未选择")
        ttk.Label(
            header,
            textvariable=self.db_label_var,
            font=("Microsoft YaHei", 9),
            foreground="gray",
            anchor=tk.W,
        ).pack(fill=tk.X, pady=(4, 0))

        # Create the status variable before the tabs: ManageTab reports its
        # initial state while it is being constructed.
        self.status_var = tk.StringVar(value="就绪")

        self.notebook = ttk.Notebook(self)
        self.notebook.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)

        self.import_tab = ImportTab(
            self.notebook, self.db, on_imported=self._on_data_changed
        )
        self.manage_tab = ManageTab(self.notebook, self.db)
        self.notebook.add(self.manage_tab, text=" 数据管理 ")
        self.notebook.add(self.import_tab, text=" 导入对话 ")

        status_frame = ttk.Frame(self)
        status_frame.pack(fill=tk.X, padx=10, pady=(0, 10))
        ttk.Label(
            status_frame,
            textvariable=self.status_var,
            relief=tk.SUNKEN,
            anchor=tk.W,
        ).pack(fill=tk.X)

        if db_path:
            explicit_path = Path(db_path).expanduser().resolve()
            try:
                explicit_mtime = explicit_path.stat().st_mtime
            except OSError:
                explicit_mtime = 0.0
            self._set_database(
                str(explicit_path),
                DatabaseCandidate(
                    path=explicit_path,
                    kind="custom",
                    mtime=explicit_mtime,
                ),
                save=False,
            )
        elif len(self._candidates) == 1:
            self._set_database(
                self._candidates[0].path,
                self._candidates[0],
                save=False,
            )
        elif len(self._candidates) > 1:
            self.after(150, self._detect_and_choose)
        else:
            self.set_status("未检测到 AstrBot 数据库；请点击“打开数据库”")

        self.notebook.select(
            self.import_tab if initial_tab == "import" else self.manage_tab
        )

        if import_file:
            self.import_tab.load_file(import_file)
            self.notebook.select(self.import_tab)

        apply_language(self)
        self.db_label_var.set(self._db_label_text())
        self.import_tab.retranslate()
        self.manage_tab.retranslate()
        self.language_var.set(
            "简体中文" if i18n.current == "zh" else "English"
        )

    def _on_language_changed(self, event=None):
        language = "zh" if self.language_var.get() == "简体中文" else "en"
        if language == i18n.current:
            return

        set_language(language)
        try:
            save_language(language)
        except OSError:
            pass

        apply_language(self)
        self.title(tr("AstrBot 对话数据管理工具 {}", __version__))
        self.db_label_var.set(self._db_label_text())
        self.status_var.set(translate_text(self.status_var.get()))
        self.import_tab.retranslate()
        self.manage_tab.retranslate()
        self.language_var.set(
            "简体中文" if language == "zh" else "English"
        )

    def _friendly_path(self, path) -> str:
        """Prefer a relative or ~-relative path for display."""

        target = Path(path)
        try:
            relative = os.path.relpath(target, Path.cwd())
            if relative != "." and not relative.startswith(".."):
                return relative
        except ValueError:
            pass

        try:
            return "~/" + target.relative_to(Path.home()).as_posix()
        except ValueError:
            return str(target)

    def _db_label_text(self) -> str:
        if not self.db_path:
            return tr("数据库：未选择")
        name = (
            translate_text(self._db_candidate.display_name)
            if self._db_candidate is not None
            else tr("数据库")
        )
        return tr(
            "数据库：{} · {}",
            name,
            self._friendly_path(self.db_path),
        )

    def set_status(self, message: str):
        if hasattr(self, "status_var"):
            self.status_var.set(translate_text(message))

    def _set_database(
        self,
        db_path: str,
        candidate: DatabaseCandidate | None = None,
        save: bool = True,
    ) -> bool:
        try:
            database = ConversationDB(db_path)
        except InvalidDatabaseError as exc:
            messagebox.showerror(
                tr("无法打开数据库"), translate_text(str(exc))
            )
            return False

        self.db = database
        self.db_path = database.db_path
        self._db_candidate = candidate
        self.db_label_var.set(self._db_label_text())

        self.import_tab.update_db(database)
        self.manage_tab.update_db(database)
        try:
            self.manage_tab._refresh()
        except Exception:
            pass

        if save:
            try:
                save_last_database(database.db_path)
            except OSError:
                pass

        self.set_status(
            tr(
                "已加载数据库：{}",
                self._friendly_path(database.db_path),
            )
        )
        self._warn_if_database_may_be_running()
        return True

    def _warn_if_database_may_be_running(self):
        if self._wal_warned or not self.db_path:
            return
        wal_path = Path(self.db_path + "-wal")
        if wal_path.exists():
            self._wal_warned = True
            messagebox.showwarning(
                tr("提示"),
                tr(
                    "检测到 SQLite WAL 文件，AstrBot 或 Launcher 可能正在运行。\n"
                    "建议先关闭它们再编辑。工具会在第一次写入前自动备份数据库。"
                ),
            )

    def _on_data_changed(self):
        self.manage_tab._refresh()
        if self.db is not None and self.db.backup_path is not None:
            message = tr(
                "数据已更新；备份：{}",
                self._friendly_path(self.db.backup_path),
            )
        else:
            message = tr("数据已更新")
        self.set_status(message)

    def _detect_and_choose(self):
        candidates = detect_databases()
        self._candidates = candidates

        if not candidates:
            messagebox.showinfo(
                tr("未检测到数据库"),
                tr(
                    "没有在 AstrBot Desktop、Launcher、CLI 或当前目录中找到有效数据库。\n"
                    "请点击“打开数据库”手动选择 data_v4.db 或 data_v3.db。"
                ),
            )
            self.set_status(tr("未检测到 AstrBot 数据库"))
            return

        if len(candidates) == 1:
            self._set_database(candidates[0].path, candidates[0])
            return

        dialog = DatabasePickerDialog(self, candidates, self._friendly_path)
        if dialog.result is not None:
            self._set_database(dialog.result.path, dialog.result)

    def _open_database(self):
        initial_dir = os.path.dirname(self.db_path) if self.db_path else None
        filepath = filedialog.askopenfilename(
            title=tr("选择 AstrBot 数据库文件"),
            filetypes=[
                (tr("SQLite 数据库"), "*.db *.sqlite *.sqlite3"),
                (tr("所有文件"), "*.*"),
            ],
            initialdir=initial_dir,
        )
        if not filepath:
            return
        self._set_database(filepath, candidate=None, save=True)


def main(argv=None):
    parser = argparse.ArgumentParser(
        prog="astrbot-conversation-manager",
        description="Browse and edit AstrBot conversation data safely.",
    )
    parser.add_argument("--db", help="Path to data_v4.db or data_v3.db")
    parser.add_argument(
        "--tab",
        choices=("manage", "import"),
        default="manage",
        help="Initial tab (default: manage)",
    )
    parser.add_argument(
        "--import-file",
        help="Load an AstrBot JSON/JSONL export at startup",
    )
    parser.add_argument(
        "--lang",
        choices=("zh", "en"),
        help="UI language (default: saved setting, or zh)",
    )
    parser.add_argument(
        "--version",
        action="version",
        version=f"%(prog)s {__version__}",
    )
    args = parser.parse_args(argv)

    if args.lang:
        set_language(args.lang)
        try:
            save_language(args.lang)
        except OSError:
            pass

    app = MainWindow(
        db_path=args.db,
        initial_tab=args.tab,
        import_file=args.import_file,
    )
    app.mainloop()
