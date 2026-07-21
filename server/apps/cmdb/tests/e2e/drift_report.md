# 字段漂移报告

扫描 78 个 model_id

## 统计
- ok(完全对齐): 11
- 缺字段或类型错: 6
- 多字段: 0
- 无 fixture: 4
- 无 expected_subset: 44
- 无 schema: 13

## 缺字段 / 类型错

| model_id | 缺字段 | 类型错 |
| --- | --- | --- |
| aliyun | expired_time, os_name |  |
| influxdb |  | https_enabled(str→bool) |
| mysql | role |  |
| network | port, soid, sys_desc |  |
| qcloud_clb | vpc |  |
| qcloud_cmq | qps |  |

## 完全对齐

- fusioninsight_cluster, fusioninsight_host, host, hwcloud_ecs, hwcloud_vpc, qcloud_bucket, qcloud_cvm, qcloud_mongodb
- qcloud_mysql, qcloud_redis, vmware

## 无 fixture 04_expected_cmdb_result.json

- aliyun_ecs
- config_file
- k8s_namespace
- redis_sentinel_enterprise
