# AstrBot 对话数据管理工具

[简体中文](README.md) | [English](README.en.md)

[![test](https://github.com/Fin1995/astrbot-conversation-manager/actions/workflows/test.yml/badge.svg)](https://github.com/Fin1995/astrbot-conversation-manager/actions/workflows/test.yml)

一个无第三方运行时依赖的 Windows 桌面小工具，用于浏览、编辑和导入 AstrBot 保存在 `data_v4.db` 中的对话数据。旧版 `data_v3.db` 只要包含相同的 `conversations` 表结构也可以打开。界面支持简体中文（默认）和英文，可在标题栏的语言选择器切换，或使用 `--lang en`。

> 非官方社区工具，与 AstrBot 官方无关联。编辑前请备份数据库，并先关闭 AstrBot / Launcher。

![数据管理](docs/images/main-window.png)

## 功能

| 功能 | 说明 |
|---|---|
| 自动识别 | 自动查找 AstrBot Desktop、Launcher、CLI 和源码目录的数据库，不写死用户名或实例 UUID |
| 对话管理 | 搜索、查看、重命名和删除对话 |
| 消息编辑 | 编辑、删除、插入、合并消息，支持按角色过滤 |
| 导入 | 读取 AstrBot 的 JSONL/JSON 导出，勾选消息后插入或合并 |
| 安全写入 | 表结构校验、SQLite 事务、首次写入前自动备份 |
| 多实例 | 检测到多个有效数据库时弹出选择窗口 |
| 无运行时依赖 | 只使用 Python 标准库和 Tkinter |
| 自动化测试 | 覆盖路径识别、数据库访问、导入解析和界面翻译 |

### 导入 AstrBot 导出

AstrBot 的 JSONL 导出是一行一个对话；即使 WebUI 中只勾选了一行，文件也可能包含多个对话。导入页会列出文件中的全部对话并显示总数，请先在左侧选择要导入的对话；工具只导入选中的对话和消息。

## 支持的 AstrBot 数据位置

AstrBot 并没有统一的数据库路径。工具会检查官方布局，并对每个候选文件做只读校验：

| 安装方式 | 默认数据库路径 |
|---|---|
| AstrBot Desktop | `%USERPROFILE%\.astrbot\data\data_v4.db` |
| AstrBot Launcher（默认） | `%USERPROFILE%\.astrbot_launcher\instances\<实例ID>\core\data\data_v4.db` |
| AstrBot Launcher（自定义数据目录） | `<数据目录>\instances\<实例ID>\core\data\data_v4.db`；数据目录从 `%APPDATA%\com.github.raven95676.astrbot-launcher\.data-dir.json` 读取 |
| AstrBot 源码 / 当前目录 | `<AstrBot 根目录>\data\data_v4.db`；可用 `ASTRBOT_ROOT` 覆盖根目录 |
| AstrBot CLI / uv 安装 | `~/.local/share/astrbot/data/data_v4.db` |
| 手动选择 | 文件选择框、`--db` 或 `ASTRBOT_CONVERSATION_DB` |

识别顺序：

1. `ASTRBOT_CONVERSATION_DB` 或 `--db`
2. 上次在界面中选择的数据库
3. `ASTRBOT_ROOT`
4. AstrBot Desktop
5. AstrBot Launcher（默认目录和自定义数据目录）
6. AstrBot CLI
7. 当前目录及最多三级父目录
8. 手动选择

每个数据目录先检查 `data_v4.db`，再检查旧版 `data_v3.db`。所有候选文件都以只读方式打开，并检查 `conversations` 表及编辑器需要的字段；无效文件会被跳过。检测到多个有效数据库时会弹出选择窗口。代码中没有写死 `C:\Users\...` 路径或 Launcher 实例 UUID。

## 截图

| 数据管理 | 导入预览 |
|---|---|
| ![数据管理](docs/images/main-window.png) | ![导入预览](docs/images/import-tab.png) |

截图展示默认的中文界面，使用 `python tools/make_demo_data.py` 生成的合成演示数据、Tk 默认主题，并让窗口在屏幕居中后截取。截图中不包含真实对话数据；可在标题栏的语言选择器切换到英文。

## 运行环境

- Windows 10 或 Windows 11
- Python 3.10 或更高版本，并带 Tkinter（python.org 的 Windows 安装包默认包含）
- 运行时不需要安装任何 pip 包

## 运行

```powershell
python run.pyw
```

或者安装后运行：

```powershell
python -m pip install .
astrbot-conversation-manager
```

常用参数：

```powershell
python run.pyw --db "C:\path\to\data_v4.db"
python run.pyw --tab import --import-file "conversations_export.jsonl"
python run.pyw --lang en
```

如果没有检测到数据库，点击 **打开数据库**，选择 `data_v4.db` 或 `data_v3.db`。

## 安全与备份

- **编辑前先关闭 AstrBot 和 Launcher。** 如果检测到 `-wal` 文件，工具会提示数据库可能正在被占用。
- 每次会话第一次写入前，会在数据库旁边创建一致性的备份：`conversation-manager-backups/<数据库名>-<时间戳>.db`。
- 写入前校验表结构，写入使用 SQLite 事务。
- 重命名对话时，如果存在 `provider_stats` 表，也会同步更新其中的 `conversation_id`。
- `token_usage` 使用与原工具相同的粗略字符估算，并不是真正的分词器；AstrBot 可能会把它用于统计。
- 建议先在数据库副本上测试编辑。

## 开发

```powershell
python -m pip install pytest
python -m pytest -q
python tools/make_demo_data.py
```

演示数据库和导出文件写入 `demo/`，不会提交到 git。测试工作流在 Windows 上使用 Python 3.10 和 3.12。

## 项目结构

```text
README.md                       中文文档（默认）
README.en.md                    英文文档
run.pyw                         源码目录启动器
src/astrbot_conversation_manager/
  app.py                        Tkinter 界面和入口
  db.py                         SQLite 访问、校验、备份
  importer.py                   JSON/JSONL 导出解析
  paths.py                      AstrBot 路径识别
  i18n.py                       中英文界面运行时翻译
tests/                          路径、数据库、导入和 i18n 测试
tools/make_demo_data.py         合成演示数据生成器
docs/images/                    README 截图
```

## 许可证

MIT，详见 [LICENSE](LICENSE)。
