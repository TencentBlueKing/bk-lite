# Blueking Lite

[![license](https://img.shields.io/badge/license-mit-brightgreen.svg?style=flat)](https://github.com/TencentBlueKing/bk-cmdb/blob/master/LICENSE.txt) [![Release Version](https://img.shields.io/badge/release-dev--in--progress-orange.svg)](https://github.com/TencentBlueKing/bk-cmdb/releases) [![PRs Welcome](https://img.shields.io/badge/PRs-welcome-brightgreen.svg)](https://github.com/TencentBlueKing/bk-cmdb/pulls) [![Ask DeepWiki](https://deepwiki.com/badge.svg)](https://deepwiki.com/TencentBlueKing/bk-lite)

---
## 📖 简介

Blueking Lite 是一个 **AI First** 的**轻量版**运维产品，具有部署资源要求低、使用成本低、渐进式体验等特点，为运维管理员提供日常运维中的必备工具。

### 🌐 在线体验

- **快速体验**: https://bklite.canway.net （微信扫码登录）
- **英文文档**: [English Documents Available](readme_en.md)
- **极速安装**: `curl -sSL https://bklite.ai/install.run| bash -`
## ✨ 核心特性

- 🎨 **简约设计**：AI 原生界面，操作简洁直观
- 📈 **渐进式体验**：循序渐进的功能引导
- ⚡ **轻量化架构**：低资源占用，快速部署

## 🚀 快速开始

- 🛠️ [本地开发与运行](DEVELOP.md)

## 🧪 测试覆盖率

![coverage](https://img.shields.io/badge/coverage-82.7%25-green)
![tests](https://img.shields.io/badge/tests-passing-brightgreen)
![modules≥80%](https://img.shields.io/badge/modules%20%E2%89%A580%25-16%2F16-blue)
![new tests](https://img.shields.io/badge/new%20tests-339-brightgreen)
![infra](https://img.shields.io/badge/tested%20with-local%20containers-informational)

> 统计口径：`apps/<module>` 业务源码覆盖率，排除 `tests/`、模块根目录 `tests.py` 与 `migrations/`。相对原始全量快照的 79.95%，本次严格业务源码覆盖率为 82.66%；新增 339 个测试用例的独立合并执行结果为 339 passed、0 failed、0 errors，最终全量结果为 26,255 passed、0 failed、0 errors。

| 模块 | 覆盖率 | 模块 | 覆盖率 |
|------|-------:|------|-------:|
| rpc | 99.44% | log | 87.48% |
| base | 98.95% | operation_analysis | 83.97% |
| job_mgmt | 95.64% | core | 83.20% |
| console_mgmt | 90.47% | mlops | 81.24% |
| alerts | 85.80% | system_mgmt | 82.40% |
| monitor | 80.17% | node_mgmt | 80.21% |
| cmdb | 82.54% | opspilot | 80.74% |
| patch_mgmt | 81.13% | apm | 88.74% |

## 🛣️ 路线图

- 📋 [版本日志](docs/changelog/release.md)

---

## 🆘 支持与帮助

- 📖 [Wiki](https://github.com/TencentBlueKing/bk-cmdb/wiki)
- 📘 [产品白皮书](https://docs.bk.tencent.com/)
- 💬 [蓝鲸论坛](https://bk.tencent.com/s-mart/community)

## 🌟 蓝鲸生态

蓝鲸智云是腾讯开源的一套完整的企业级研发运营一体化平台：

- **[BK-CI](https://github.com/Tencent/bk-ci)**：蓝鲸持续集成平台，开源的持续集成和持续交付系统
- **[BK-BCS](https://github.com/Tencent/bk-bcs)**：蓝鲸容器管理平台，基于容器技术的微服务编排管理平台
- **[BK-PaaS](https://github.com/Tencent/bk-PaaS)**：蓝鲸 PaaS 平台，开放式的 SaaS 开发平台
- **[BK-SOPS](https://github.com/Tencent/bk-sops)**：标准运维，可视化的任务流程编排和执行系统

## 🤝 参与贡献

我们欢迎所有形式的贡献，包括但不限于：

- 🐛 提交 Bug 报告
- 💡 提出新功能建议
- 📝 改进文档
- 🔧 提交代码修复

如果你有好的意见或建议，欢迎给我们提 [Issues](https://github.com/TencentBlueKing/bk-lite/issues) 或 [Pull Requests](https://github.com/TencentBlueKing/bk-lite/pulls)，为蓝鲸开源社区贡献力量。

### 🎉 开源激励

[腾讯开源激励计划](https://opensource.tencent.com/contribution) 鼓励开发者的参与和贡献，期待你的加入！

## 📄 开源协议

本项目基于 [MIT 协议](LICENSE.txt) 开源。

我们承诺未来不会更改适用于交付给任何人的当前项目版本的开源许可证（MIT 协议）。

## 👥 贡献者

<div align="center">

![Contributors](https://contrib.nn.ci/api?repo=TencentBlueKing/bk-lite)

</div>
