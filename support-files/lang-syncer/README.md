# 语言包同步工具

提供语言包与 Notion 数据库之间的双向同步功能。

## 功能特性

- ✅ **Web 前端语言包同步** - 支持 JSON 格式
- ✅ **Server 后端语言包同步** - 支持 YAML 格式
- ✅ **双向同步** - 支持推送和拉取
- ✅ **增量更新** - 自动识别新增和删除的 key
- ✅ **批量处理** - 支持多应用配置

## 环境配置

在 `.env` 文件中配置以下环境变量：

```bash
# Notion API Token
NOTION_TOKEN=your_notion_token_here

# Web 前端语言包配置（格式：app_name:database_id,app_name:database_id）
WEB_LANG_CONFIG=node-manager:your_database_id,another-app:another_database_id

# Server 后端语言包配置（格式：app_name:database_id,app_name:database_id）
SERVER_LANG_CONFIG=monitor:your_database_id,log:another_database_id,node_mgmt:another_database_id
```

## 使用方法

### Web 前端语言包

#### 推送到 Notion
```bash
uv run main.py push_web_pack
```

功能：
1. 读取 `web/src/app/{app_name}/locales/` 下的 JSON 文件
2. 扁平化为 key-value 格式
3. 与 Notion 数据库比对，删除 Notion 中本地已不存在的 key
4. 批量写入新增数据到 Notion

#### 从 Notion 同步
```bash
uv run main.py sync_web_pack
```

功能：
1. 从 Notion 获取所有语言包数据
2. 按语言分组，构建扁平化字典
3. 还原为嵌套 JSON 结构
4. 写入本地 JSON 文件（覆盖）

### Server 后端语言包

#### 推送到 Notion
```bash
uv run main.py push_server_pack
```

功能：
1. 读取 `server/apps/{app_name}/language/` 下的 YAML 文件
2. 扁平化为 key-value 格式
3. 与 Notion 数据库比对，删除 Notion 中本地已不存在的 key
4. 批量写入新增数据到 Notion

#### 从 Notion 同步
```bash
uv run main.py sync_server_pack
```

功能：
1. 从 Notion 获取所有语言包数据
2. 按语言分组，构建扁平化字典
3. 还原为嵌套 YAML 结构
4. 写入本地 YAML 文件（覆盖）

## 文件结构

```
support-files/lang-syncer/
├── main.py              # CLI 入口，负责调度
├── utils.py             # 通用工具函数（JSON/YAML 处理）
├── web_syncer.py        # Web 前端语言包同步器
├── server_syncer.py     # Server 后端语言包同步器
├── notion_client.py     # Notion API 客户端
├── .env                 # 环境变量配置
└── README.md            # 使用文档
```

## Notion 数据库结构

### Web 前端

| 列名 | 类型  | 说明                          |
| ---- | ----- | ----------------------------- |
| 名称 | Title | 翻译 key（如 common.actions） |
| zh   | Text  | 中文翻译                      |
| en   | Text  | 英文翻译                      |

### Server 后端

| 列名    | 类型  | 说明                                  |
| ------- | ----- | ------------------------------------- |
| 名称    | Title | 翻译 key（如 monitor_object_type.OS） |
| zh-Hans | Text  | 简体中文翻译                          |
| en      | Text  | 英文翻译                              |

## 本地语言包格式

### Web 前端 - JSON 格式

路径：`web/src/app/{app_name}/locales/{lang}.json`

```json
{
  "common": {
    "actions": "操作",
    "save": "保存"
  }
}
```

### Server 后端 - YAML 格式

路径：`server/apps/{app_name}/language/{lang}.yaml`

```yaml
monitor_object_type:
  OS: 操作系统
  Web: 网络
  Database: 数据库
```

## 注意事项

1. **备份数据**：首次使用前建议备份现有语言包
2. **环境变量**：确保 `.env` 文件配置正确
3. **Database ID**：Notion Database ID 可以去掉连字符或保留（工具会自动处理）
4. **文件编码**：所有文件使用 UTF-8 编码
5. **同步方向**：
   - `push_*` 命令：本地 → Notion（以本地为准）
   - `sync_*` 命令：Notion → 本地（以 Notion 为准）

## 工作流建议

1. **开发阶段**：在本地修改语言包后，使用 `push_*` 推送到 Notion
2. **翻译阶段**：在 Notion 中完成翻译工作
3. **部署前**：使用 `sync_*` 同步最新翻译到本地
4. **版本控制**：同步后提交到 Git

## 故障排查

### 推送失败
- 检查 Notion Token 是否有效
- 检查 Database ID 是否正确
- 检查本地语言包文件格式是否正确

### 同步失败
- 检查 Notion 数据库结构是否匹配
- 检查列名是否正确（Web: 名称、zh、en；Server: 名称、zh-Hans、en）
- 检查是否有足够的文件写入权限

## 依赖

- Python 3.8+
- pandas
- pyyaml
- loguru
- fire
- python-dotenv
- tqdm
- requests
