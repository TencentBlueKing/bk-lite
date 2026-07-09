# #0005 vmware 插件分组规则编辑报错"监控实例与监控对象不匹配",子对象丢失

- 2026-07-08T09:41:07Z `issue`: vmware 插件分组规则编辑报错"监控实例与监控对象不匹配",子对象丢失 [web/src/app/monitor/(pages)/event/strategy/detail]
- 2026-07-08T09:44:26Z `attempt`: 已锁定 organization_rule update 校验的根因:create_default_rule 给子对象(DataStorage/ESXI/VM 等 derivative)自动建规则时,把 rule.monitor_object_id 设为子对象,但 monitor_instance_id 沿用父实例;_validate_rule_binding 在 instance.monitor_object_id != rule.monitor_object_id 时抛"监控实例与监控对象不匹配",直接卡掉 derivative 子规则的编辑。100374c54 引入该校验时未兼容 derivative 关系 [server/apps/monitor/views/organization_rule.py] (worked)
- 2026-07-08T09:51:23Z `fix`: vmware 父实例自动建子规则编辑失败:已在 _validate_rule_binding 中为 derivative 子对象放行父实例绑定(MonitorObject.parent_id == instance.monitor_object_id),保留 base 严格校验;新增 3 个测试覆盖 derivative-父实例合法、derivative-无关实例仍拒绝、PUT 端到端 200 [server/apps/monitor/views/organization_rule.py]
