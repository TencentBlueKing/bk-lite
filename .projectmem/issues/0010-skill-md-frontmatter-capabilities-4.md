# #0010 技能包 SKILL.md frontmatter 中的 capabilities 字段不生效，链路上至少 4 处会把它丢成空集

- 2026-07-09T03:04:18Z `issue`: 技能包 SKILL.md frontmatter 中的 capabilities 字段不生效，链路上至少 4 处会把它丢成空集 [server/apps/opspilot/services/skill_package/importer.py:71-74; server/apps/opspilot/services/skill_package/materializer.py:92-98; server/apps/opspilot/services/skill_package/runtime.py:189-208; server/apps/opspilot/serializers/llm_serializer.py:160-170]
- 2026-07-09T03:30:30Z `attempt`: 把 _manifest_with_storage_overlay 改成始终回读磁盘 skill.yaml + SKILL.md frontmatter,移除三个键都存在就早返回的逻辑;优先级 SKILL.md > skill.yaml > DB manifest [server/apps/opspilot/services/skill_package/runtime.py:195-242] (worked)
- 2026-07-09T03:30:30Z `fix`: chain 路径在每次请求都从磁盘回读 SKILL.md frontmatter 和 skill.yaml,覆盖 DB manifest 的 capabilities/reports/workflows;SKILL.md frontmatter 最高优先级,支持热生效 [server/apps/opspilot/services/skill_package/runtime.py:1-9,195-242]
