# Design: Playbook 文件内容预览

## Context

### 现状

Playbook 模板库页面已实现：
- 文件列表树形展示（`file_list` 字段，由 `_build_file_tree()` 生成）
- README 预览（使用 `MarkdownRenderer` 组件）
- 整包下载功能

缺失：
- 单个文件内容预览（"预览"按钮无点击事件）
- 后端无获取单文件内容的 API

### 技术栈

- **后端**: Django + MinIO 存储
- **前端**: Next.js + Ant Design + highlight.js（项目已有）
- **压缩包格式**: ZIP / tar.gz / tgz

### 约束

- Playbook 文件存储在 MinIO，通过 Django FileField 访问
- 现有解析逻辑在 `server/apps/job_mgmt/serializers/playbook.py`
- 前端已有 `highlight.js` 依赖，用于 opspilot 聊天代码高亮

## Goals / Non-Goals

**Goals:**
- 用户可预览 Playbook 压缩包内任意文本文件
- 代码文件有语法高亮（YAML、Markdown、Python、Shell、JSON、Jinja2）
- 合理的文件大小限制，防止浏览器卡顿

**Non-Goals:**
- 文件编辑/保存功能
- 二进制文件预览（图片、编译产物等）
- 文件搜索功能
- 多文件同时预览

## Decisions

### Decision 1: 后端 API 设计

**选择**: 新增 `preview_file` action，按需解压单个文件

```
GET /job_mgmt/api/playbook/{id}/preview_file/?file_path=roles/example/tasks/main.yml
```

**返回**:
```json
{
  "file_name": "main.yml",
  "file_path": "roles/example/tasks/main.yml",
  "content": "---\n- name: Print hello\n  debug:\n    msg: \"{{ message }}\"",
  "file_type": "yaml",
  "file_size": 128
}
```

**备选方案**:
1. ~~在 `getPlaybookDetail` 时返回所有文件内容~~ - 压缩包可能很大，浪费带宽
2. ~~前端下载整包后本地解压~~ - 浏览器解压大文件性能差，且需要额外依赖

**理由**: 按需加载最节省资源，且复用现有的压缩包解析逻辑。

### Decision 2: 文件类型检测

**选择**: 基于文件扩展名映射

```python
FILE_TYPE_MAP = {
    ".yml": "yaml",
    ".yaml": "yaml",
    ".md": "markdown",
    ".py": "python",
    ".sh": "bash",
    ".json": "json",
    ".j2": "jinja2",
    ".jinja2": "jinja2",
    ".txt": "text",
    ".cfg": "ini",
    ".ini": "ini",
    ".conf": "ini",
}
```

**备选方案**:
1. ~~使用 python-magic 检测 MIME 类型~~ - 增加依赖，对文本文件区分度不高

**理由**: Playbook 文件类型有限且规范，扩展名足够准确。

### Decision 3: 前端代码高亮

**选择**: 复用项目已有的 `highlight.js`

```tsx
import hljs from 'highlight.js';
import 'highlight.js/styles/atom-one-dark.css';

// 按需注册语言
import 'highlight.js/lib/languages/yaml';
import 'highlight.js/lib/languages/python';
import 'highlight.js/lib/languages/bash';
import 'highlight.js/lib/languages/json';
import 'highlight.js/lib/languages/markdown';
import 'highlight.js/lib/languages/django'; // for jinja2
```

**备选方案**:
1. ~~引入 react-syntax-highlighter~~ - 新增依赖，项目已有 highlight.js
2. ~~使用 Monaco Editor~~ - 过重，预览不需要编辑功能

**理由**: 复用现有依赖，保持一致性，减少包体积。

### Decision 4: 文件大小限制

**选择**: 后端限制 1MB，超过返回错误

```python
MAX_PREVIEW_SIZE = 1 * 1024 * 1024  # 1MB

if file_size > MAX_PREVIEW_SIZE:
    return Response(
        {"detail": "文件过大，不支持预览", "file_size": file_size},
        status=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE
    )
```

**理由**: 
- 1MB 足够覆盖绝大多数 Ansible 配置文件
- 防止大文件导致浏览器卡顿
- 前端显示友好提示，引导用户下载查看

### Decision 5: 二进制文件处理

**选择**: 后端检测，返回 400 错误

```python
BINARY_EXTENSIONS = {".pyc", ".pyo", ".so", ".dll", ".exe", ".bin", ".tar", ".gz", ".zip"}

def is_binary_file(file_path: str, content: bytes) -> bool:
    # 1. 检查扩展名
    if any(file_path.lower().endswith(ext) for ext in BINARY_EXTENSIONS):
        return True
    # 2. 检查内容是否包含 null 字节
    return b'\x00' in content[:8192]
```

**理由**: 二进制文件无法有意义地显示为文本，提前拦截避免乱码。

### Decision 6: 前端 UI 组件

**选择**: 在现有 View Modal 内新增子弹窗

```
┌─────────────────────────────────────────────────────────────┐
│  playbook-template  v1.0.0                    [下载] [升级] │
├─────────────────────────────────────────────────────────────┤
│  基本信息 | 参数说明 | 文件列表 | README                      │
├─────────────────────────────────────────────────────────────┤
│  📁 playbook-template                                       │
│    📄 README.md                              [预览] ←点击    │
│    📄 playbook.yml                           [预览]         │
│    📁 roles                                                 │
│      📁 example                                             │
│        📁 tasks                                             │
│          📄 main.yml                         [预览]         │
└─────────────────────────────────────────────────────────────┘
                          │
                          ▼ 点击预览
┌─────────────────────────────────────────────────────────────┐
│  预览: main.yml                                        [×]  │
├─────────────────────────────────────────────────────────────┤
│  ---                                                        │
│  - name: Print hello message                                │
│    debug:                                                   │
│      msg: "{{ message }}"                                   │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

**理由**: 子弹窗保持上下文，用户可快速切换预览不同文件。

## Risks / Trade-offs

| Risk | Impact | Mitigation |
|------|--------|------------|
| 压缩包损坏导致解压失败 | 中 | 捕获异常，返回友好错误信息 |
| 大量并发预览请求 | 低 | 每次请求独立解压，无状态；必要时可加缓存 |
| 文件路径注入攻击 | 高 | 验证 file_path 在压缩包 namelist 内，禁止 `..` |
| 编码问题导致乱码 | 低 | 使用 `errors="ignore"` 容错解码 |

## 安全考虑

### 路径遍历防护

```python
def validate_file_path(file_path: str, valid_paths: list) -> bool:
    """验证文件路径合法性"""
    # 1. 禁止路径遍历
    if ".." in file_path or file_path.startswith("/"):
        return False
    # 2. 必须在压缩包文件列表中
    return file_path in valid_paths
```

### 权限复用

复用现有 `@HasPermission("playbook_library-View")` 装饰器，无需新增权限点。
