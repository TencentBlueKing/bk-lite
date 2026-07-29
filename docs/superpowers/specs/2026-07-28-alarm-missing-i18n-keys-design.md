# 告警中心缺失翻译 Key 修复设计

## 目标

只修复告警中心当前确认的 8 个不存在的翻译调用，避免界面直接显示
`confirm`、`cancel`、`common.month`、`common.day`、`common.previous` 和
`common.level`。

## 范围

- 两个告警操作组件中的 `confirm`、`cancel` 调用改为已存在的
  `common.confirm`、`common.cancel`。
- 事件热力图的月、日、上一时间段和级别文案改为告警模块自有的新 key。
- 在 `alarm/locales/zh.json` 和 `alarm/locales/en.json` 中成对补齐热力图文案。
- 扩展告警 i18n 回归测试，验证源码使用正确 key、对应中英文值存在。

不处理本轮审计发现的其它硬编码文案，也不调整告警模块对其它应用语言包的依赖。

## 测试接缝

测试以告警操作组件源码和告警中英文语言包为接缝：

1. 两个操作组件必须使用 `common.confirm`、`common.cancel`。
2. 热力图必须使用告警模块自有的 4 个 key。
3. 4 个热力图 key 在中英文语言包中都存在，并具有明确的已知翻译。

先让扩展后的测试在当前实现上失败，再修改源码和语言包使其通过。

