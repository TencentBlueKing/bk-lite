# #0002 监控公式结果单位实现仍会在切换公式时继承单指标单位，并用第一指标枚举单位影响阈值输入

- 2026-07-08T07:56:39Z `issue`: 监控公式结果单位实现仍会在切换公式时继承单指标单位，并用第一指标枚举单位影响阈值输入 [web/src/app/monitor/(pages)/event/strategy/detail/page.tsx]
- 2026-07-08T08:01:52Z `attempt`: 新增公式模式切换与阈值枚举 helper，并修正详情页与告警条件表单以避免继承单指标单位和枚举阈值误判 [web/src/app/monitor/(pages)/event/strategy/detail/page.tsx] (worked)
- 2026-07-08T08:02:47Z `fix`: 修正公式模式切换默认结果单位为 percent，并让公式模式阈值输入忽略首指标枚举单位，聚焦脚本测试与定点 eslint 已通过 [web/src/app/monitor/(pages)/event/strategy/detail/page.tsx]
- 2026-07-08T08:09:31Z `fix`: 公式模式切换现在默认 percent，公式阈值枚举判断不再依赖首个指标单位；聚焦测试、改动文件 lint、type-check 已通过 [web/src/app/monitor/(pages)/event/strategy/detail/page.tsx]
