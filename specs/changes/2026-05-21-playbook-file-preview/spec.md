# Playbook 文件内容预览功能

Status: done

## Migration Context

- Legacy source: `openspec/changes/archive/2026-05-21-playbook-file-preview/`
- Legacy state: `archived`
- 内容按原始 artifact 合并，未把 delta 自动写回长期 capability。

## Problem and Proposal

## 问题

在 Playbook 模板库页面 (`/job/template/playbook-library`)，文件列表中每个文件旁边都有"预览"链接，但点击后没有任何反应。

**现状**：
- 前端 UI 已渲染"预览"按钮
- 按钮没有绑定 `onClick` 事件
- 后端没有提供获取单个文件内容的 API

```tsx
// web/src/app/job/(pages)/template/playbook-library/page.tsx (Line 377-380)
{node.type === 'file' && (
  <a className="text-[var(--color-primary)] text-sm cursor-pointer">
    {t('job.preview')}  // ← 只有文字，没有点击事件
  </a>
)}
```

## 目标

实现 Playbook 压缩包内单个文件的预览功能，用户点击"预览"后能在弹窗中查看文件内容。

## 范围

### 包含
- 后端：新增 API 获取 Playbook 压缩包内指定文件的内容
- 前端：实现预览弹窗，支持代码高亮显示

### 不包含
- 文件编辑功能
- 二进制文件预览（图片等）
- 大文件处理（超过合理大小的文件）

## 方案概述

```
┌─────────────────────────────────────────────────────────────────┐
│                        用户交互流程                              │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│  1. 用户点击文件列表中的"预览"                                    │
│                    │                                            │
│                    ▼                                            │
│  2. 前端调用 GET /job_mgmt/api/playbook/{id}/preview_file/      │
│     参数: file_path=roles/example/tasks/main.yml                │
│                    │                                            │
│                    ▼                                            │
│  3. 后端从 MinIO 读取压缩包，解压指定文件，返回内容               │
│     返回: { content: "---\n- name: ...", file_type: "yaml" }    │
│                    │                                            │
│                    ▼                                            │
│  4. 前端弹窗显示文件内容，根据 file_type 应用语法高亮             │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
```

### 后端

新增 `preview_file` action：
- 路径：`GET /job_mgmt/api/playbook/{id}/preview_file/`
- 参数：`file_path` (文件在压缩包内的相对路径)
- 返回：`{ content: string, file_type: string, file_name: string }`
- 限制：文件大小上限 1MB，仅支持文本文件

### 前端

1. 新增 `previewPlaybookFile` API 调用
2. 给"预览"按钮添加 `onClick` 事件
3. 新增预览弹窗组件，使用 `react-syntax-highlighter` 或类似库实现代码高亮
4. 支持的文件类型高亮：YAML、Markdown、Python、Shell、JSON、Jinja2

## 验收标准

1. 点击文件列表中的"预览"按钮，弹出预览弹窗
2. 弹窗显示文件内容，YAML/Markdown 等文件有语法高亮
3. 大文件（>1MB）显示友好提示，不加载内容
4. 二进制文件显示"不支持预览"提示
5. 弹窗可关闭，关闭后返回文件列表视图

## Implementation Decisions

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

## Legacy Metadata

```yaml
schema: spec-driven
created: 2026-05-20
```

## Capability Deltas

### playbook-file-preview

## ADDED Requirements

### Requirement: 后端提供文件内容预览 API

系统 SHALL 提供 API 端点 `GET /job_mgmt/api/playbook/{id}/preview_file/`，允许用户获取 Playbook 压缩包内指定文件的内容。

**请求参数**:
- `file_path` (query, required): 文件在压缩包内的相对路径

**响应格式**:
```json
{
  "file_name": "main.yml",
  "file_path": "roles/example/tasks/main.yml",
  "content": "---\n- name: Print hello\n  debug:\n    msg: \"{{ message }}\"",
  "file_type": "yaml",
  "file_size": 128
}
```

**权限**: 复用 `playbook_library-View` 权限

#### Scenario: 成功预览 YAML 文件
- **WHEN** 用户请求 `GET /job_mgmt/api/playbook/1/preview_file/?file_path=roles/example/tasks/main.yml`
- **THEN** 系统返回 200，响应包含 `content` 字段为文件内容，`file_type` 为 `yaml`

#### Scenario: 成功预览 Markdown 文件
- **WHEN** 用户请求 `GET /job_mgmt/api/playbook/1/preview_file/?file_path=README.md`
- **THEN** 系统返回 200，响应包含 `content` 字段为文件内容，`file_type` 为 `markdown`

#### Scenario: 文件路径不存在
- **WHEN** 用户请求的 `file_path` 不在压缩包文件列表中
- **THEN** 系统返回 404，响应包含错误信息 `{"detail": "文件不存在"}`

#### Scenario: 缺少 file_path 参数
- **WHEN** 用户请求未提供 `file_path` 参数
- **THEN** 系统返回 400，响应包含错误信息 `{"detail": "缺少 file_path 参数"}`

---

### Requirement: 文件大小限制

系统 SHALL 限制可预览文件的最大大小为 1MB。

#### Scenario: 文件超过大小限制
- **WHEN** 用户请求预览的文件大小超过 1MB
- **THEN** 系统返回 413，响应包含 `{"detail": "文件过大，不支持预览", "file_size": <actual_size>}`

#### Scenario: 文件在大小限制内
- **WHEN** 用户请求预览的文件大小不超过 1MB
- **THEN** 系统正常返回文件内容

---

### Requirement: 二进制文件检测

系统 SHALL 检测并拒绝预览二进制文件。

**二进制文件判定规则**:
1. 文件扩展名为 `.pyc`, `.pyo`, `.so`, `.dll`, `.exe`, `.bin`, `.tar`, `.gz`, `.zip` 等
2. 文件内容前 8KB 包含 null 字节 (`\x00`)

#### Scenario: 请求预览二进制文件
- **WHEN** 用户请求预览 `.pyc` 或其他二进制文件
- **THEN** 系统返回 400，响应包含 `{"detail": "不支持预览二进制文件"}`

#### Scenario: 请求预览文本文件
- **WHEN** 用户请求预览 `.yml`, `.md`, `.py`, `.sh` 等文本文件
- **THEN** 系统正常返回文件内容

---

### Requirement: 路径安全验证

系统 SHALL 验证 `file_path` 参数，防止路径遍历攻击。

#### Scenario: 路径包含 ..
- **WHEN** 用户请求 `file_path=../../../etc/passwd`
- **THEN** 系统返回 400，响应包含 `{"detail": "非法文件路径"}`

#### Scenario: 路径以 / 开头
- **WHEN** 用户请求 `file_path=/etc/passwd`
- **THEN** 系统返回 400，响应包含 `{"detail": "非法文件路径"}`

#### Scenario: 合法相对路径
- **WHEN** 用户请求 `file_path=roles/example/tasks/main.yml`
- **THEN** 系统正常处理请求

---

### Requirement: 前端预览按钮绑定点击事件

前端 SHALL 为文件列表中的"预览"按钮绑定点击事件，点击后调用预览 API 并显示内容。

#### Scenario: 点击预览按钮
- **WHEN** 用户在文件列表中点击某文件的"预览"按钮
- **THEN** 系统调用 `GET /job_mgmt/api/playbook/{id}/preview_file/?file_path=<path>` 获取内容
- **AND** 弹出预览弹窗显示文件内容

#### Scenario: 预览加载中状态
- **WHEN** 用户点击预览按钮，API 请求进行中
- **THEN** 弹窗显示加载状态（Spin 组件）

#### Scenario: 预览失败
- **WHEN** API 返回错误（404/400/413）
- **THEN** 弹窗显示错误信息

---

### Requirement: 前端代码语法高亮

前端 SHALL 根据文件类型对预览内容应用语法高亮。

**支持的文件类型**:
| 扩展名 | 高亮语言 |
|--------|----------|
| .yml, .yaml | yaml |
| .md | markdown |
| .py | python |
| .sh | bash |
| .json | json |
| .j2, .jinja2 | django (jinja2) |
| 其他 | plaintext |

#### Scenario: YAML 文件高亮
- **WHEN** 预览 `.yml` 文件
- **THEN** 内容使用 YAML 语法高亮显示

#### Scenario: Python 文件高亮
- **WHEN** 预览 `.py` 文件
- **THEN** 内容使用 Python 语法高亮显示

#### Scenario: 未知类型文件
- **WHEN** 预览 `.txt` 或无扩展名文件
- **THEN** 内容以纯文本显示，无高亮

---

### Requirement: 预览弹窗 UI

前端 SHALL 提供预览弹窗，包含以下元素：
- 标题：显示文件名
- 内容区：显示文件内容（带语法高亮）
- 关闭按钮：关闭弹窗

#### Scenario: 打开预览弹窗
- **WHEN** 用户点击预览按钮且 API 返回成功
- **THEN** 弹窗标题显示文件名（如 "预览: main.yml"）
- **AND** 内容区显示文件内容

#### Scenario: 关闭预览弹窗
- **WHEN** 用户点击弹窗关闭按钮或弹窗外区域
- **THEN** 弹窗关闭，返回文件列表视图

#### Scenario: 长文件滚动
- **WHEN** 文件内容超过弹窗可视区域
- **THEN** 内容区可滚动查看完整内容

## Work Checklist

## 1. 后端 API 实现

- [x] 1.1 在 `server/apps/job_mgmt/serializers/playbook.py` 添加 `extract_file_from_archive()` 函数，支持从 ZIP/tar.gz 中提取单个文件内容
- [x] 1.2 在 `server/apps/job_mgmt/serializers/playbook.py` 添加文件类型检测函数 `get_file_type()`，基于扩展名返回语言类型
- [x] 1.3 在 `server/apps/job_mgmt/serializers/playbook.py` 添加二进制文件检测函数 `is_binary_file()`
- [x] 1.4 在 `server/apps/job_mgmt/serializers/playbook.py` 添加路径安全验证函数 `validate_file_path()`
- [x] 1.5 在 `server/apps/job_mgmt/views/playbook.py` 添加 `preview_file` action，实现文件预览 API
- [x] 1.6 后端单元测试：测试正常预览、文件不存在、文件过大、二进制文件、路径遍历等场景

## 2. 前端 API 层

- [x] 2.1 在 `web/src/app/job/api/index.ts` 添加 `previewPlaybookFile()` API 调用函数
- [x] 2.2 在 `web/src/app/job/types/index.ts` 添加 `PlaybookFilePreview` 类型定义

## 3. 前端 UI 实现

- [x] 3.1 在 `web/src/app/job/(pages)/template/playbook-library/page.tsx` 添加文件预览状态变量（`previewModalOpen`, `previewContent`, `previewLoading` 等）
- [x] 3.2 在 `web/src/app/job/(pages)/template/playbook-library/page.tsx` 实现 `handlePreviewFile()` 函数，调用 API 获取文件内容
- [x] 3.3 修改 `renderFileTree()` 函数，为"预览"按钮添加 `onClick` 事件
- [x] 3.4 实现文件预览弹窗组件，包含标题、内容区（带语法高亮）、关闭按钮
- [x] 3.5 集成 highlight.js 实现代码语法高亮，支持 yaml/markdown/python/bash/json/django 语言
- [x] 3.6 处理错误状态：文件不存在、文件过大、二进制文件等，显示友好提示

## 4. 国际化

- [x] 4.1 在 `web/src/app/job/locales/zh.json` 添加预览相关文案（预览弹窗标题、错误提示等）
- [x] 4.2 在 `web/src/app/job/locales/en.json` 添加对应英文文案

## 5. 验证

- [x] 5.1 手动测试：预览 YAML 文件，确认语法高亮正常
- [x] 5.2 手动测试：预览 Markdown 文件，确认语法高亮正常
- [x] 5.3 手动测试：预览不存在的文件，确认显示错误提示
- [x] 5.4 手动测试：关闭预览弹窗，确认返回文件列表视图
- [x] 5.5 代码检查：运行 `cd web && pnpm lint && pnpm type-check` 确认无错误
