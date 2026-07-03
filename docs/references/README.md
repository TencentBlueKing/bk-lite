# References —— 外部参考资料

> 给 Agent 喂的「外部知识」目录。约定用 `*-llms.txt`(纯文本、面向 LLM 的精简文档),放工具/框架的权威说明,避免 Agent 凭过时记忆作答。

## 命名约定

```
<主题>-llms.txt        # 例:uv-llms.txt、nixpacks-llms.txt
<主题>-reference.md    # 富格式参考(可选)
```

## 建议纳入的参考(按本仓技术栈)

| 文件(建议) | 内容 | 来源 |
|-------------|------|------|
| `uv-llms.txt` | uv 包管理(server/agents/algorithms 均用) | https://docs.astral.sh/uv/ |
| `django-llms.txt` | Django 4.2 要点 | Django 官方文档 |
| `nextjs-llms.txt` | Next.js 16 App Router | Next.js 官方 |
| `bentoml-llms.txt` | algorithms 服务形态 | BentoML 官方 |
| `tauri-llms.txt` | mobile 桌面/Android 打包 | Tauri 官方 |
| `falkordb-llms.txt` | CMDB 图查询语法(**非 Neo4j**) | FalkorDB 官方 |

## 已有内部参考(就近,不复制到此)

- 设计 token:[web/DESIGN.md](../../web/DESIGN.md)
- 测试指南:`server/docs/testing-guide.md`
- 设计系统 / UI:[spec/design_ui.md](../../spec/design_ui.md)

> 加新参考时优先放官方的「面向 LLM」精简版;无则裁剪官方文档为纯文本。体积大的不入库,留 URL + 摘要即可。
> TODO: 实际拉取并裁剪上表 llms.txt(需联网,按需逐个添加)。
