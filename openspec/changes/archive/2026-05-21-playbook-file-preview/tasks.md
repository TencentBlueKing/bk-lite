# Tasks: Playbook 文件预览

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
