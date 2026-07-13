# #0006 网络设备(华为 Telegraf 插件)实例识别失败:network device instance requires cloud_region and ip

- 2026-07-08T10:26:28Z `issue`: 网络设备(华为 Telegraf 插件)实例识别失败:network device instance requires cloud_region and ip [server/apps/monitor/views]
- 2026-07-08T10:28:58Z `attempt`: 根因定位:前端 useDataMapper 在提交前对 instance_id 做了 FNV-1a + base64 哈希截断(16 字符),后端 network device identity adapter 无法从哈希串切出 cloud_region/ip,导致 "实例识别失败: network device instance requires cloud_region and ip" [web/src/app/monitor/hooks/integration/useDataMapper.ts:316-321] (failed)
