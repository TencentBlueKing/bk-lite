# Playbook 文件内容预览功能

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
