# Lang Syncer

语言包同步工具 - 提供语言包与 Notion 数据库之间的双向同步功能。

## 功能特性

- 🔄 双向同步：支持推送本地语言包到 Notion 和从 Notion 同步语言包到本地
- 🌐 多端支持：同时支持 Web 前端和 Server 后端语言包同步
- 📦 配置灵活：通过环境变量配置多个应用的语言包路径
- 🚀 简单易用：提供 CLI 命令行工具和 Makefile 快捷命令

## 项目结构

```
lang-syncer/
├── src/
│   └── lang_syncer/         # 核心源代码包
│       ├── __init__.py
│       ├── cli.py           # CLI 命令行接口
│       ├── config.py        # 配置管理
│       ├── exceptions.py    # 自定义异常
│       ├── utils.py         # 工具函数
│       ├── notion_helper.py # Notion API 封装
│       ├── base_syncer.py   # 同步器基类
│       ├── web_syncer.py    # Web 语言包同步器
│       └── server_syncer.py # Server 语言包同步器
├── lang-syncer.py           # 主入口脚本
├── pyproject.toml           # 项目配置
├── Makefile                 # 快捷命令
├── .env                     # 环境变量配置
└── README.md                # 项目文档
```

## 安装

```bash
# 安装依赖
make install

# 或使用 uv 直接安装
uv sync
```

## 配置

在项目根目录创建 `.env` 文件，配置以下环境变量：

```bash
# Notion API Token (必需)
NOTION_TOKEN=your_notion_token_here

# Web 前端语言包配置 (可选)
# 格式: app_name:database_id:lang_pack_path,another_app:database_id:path
WEB_LANG_CONFIG=app1:db_id_1:/path/to/web/lang,app2:db_id_2:/path/to/web/lang2

# Server 后端语言包配置 (可选)
# 格式同上
SERVER_LANG_CONFIG=app1:db_id_3:/path/to/server/lang,app2:db_id_4:/path/to/server/lang2
```

## 使用方法

### 使用 Makefile 命令（推荐）

```bash
# 同步所有语言包（推送 + 同步 Web 和 Server）
make sync-all

# Web 前端语言包操作
make push-web    # 推送到 Notion
make sync-web    # 从 Notion 同步

# Server 后端语言包操作
make push-server # 推送到 Notion
make sync-server # 从 Notion 同步

# 清理缓存
make clean
```

### 使用 CLI 命令

```bash
# 推送 Web 前端语言包到 Notion
uv run lang-syncer.py push_web_pack

# 从 Notion 同步 Web 前端语言包
uv run lang-syncer.py sync_web_pack

# 推送 Server 后端语言包到 Notion
uv run lang-syncer.py push_server_pack

# 从 Notion 同步 Server 后端语言包
uv run lang-syncer.py sync_server_pack
```

## 开发

```bash
# 安装开发依赖
uv sync

# 运行测试（如有）
pytest

# 清理临时文件
make clean
```

## 许可证

参见项目根目录 LICENSE 文件

## 注意事项

1. 确保 `.env` 文件中的 `NOTION_TOKEN` 已正确配置
2. 语言包路径需要使用绝对路径
3. 配置多个应用时，使用逗号分隔，格式为 `app_name:database_id:lang_pack_path`
4. 首次使用前请确保 Notion 数据库结构符合要求
