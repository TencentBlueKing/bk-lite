import { IntegrationLogInstance } from '@/app/log/types/integration';
import { TableDataItem } from '@/app/log/types';
import { useRedisFilebeatFormItems } from '../../common/redisFilebeatFormItems';
import { cloneDeep } from 'lodash';

export const useRedisFilebeatConfig = () => {
  const commonFormItems = useRedisFilebeatFormItems();
  const pluginConfig = {
    collector: 'Filebeat',
    collect_type: 'redis',
    icon: 'redis'
  };

  return {
    getConfig: (extra: {
      dataSource?: IntegrationLogInstance[];
      mode: 'manual' | 'auto' | 'edit';
      onTableDataChange?: (data: IntegrationLogInstance[]) => void;
    }) => {
      const configs = {
        auto: {
          formItems: commonFormItems.getCommonFormItems({
            disabledFormItems: {},
            hiddenFormItems: {}
          }),
          initTableItems: {},
          defaultForm: {
            log: {
              enabled: true,
              paths: ['/var/log/redis/redis-server.log']
            },
            slowlog: {
              enabled: false,
              hosts: [],
              password: ''
            }
          },
          columns: [],
          getParams: (row: IntegrationLogInstance, config: TableDataItem) => {
            const dataSource = cloneDeep(config.dataSource || []);

            // Flat structure with fields: log_enabled, log_paths, slowlog_enabled, slowlog_hosts, slowlog_password
            const configData = {
              log_enabled: !!row.log?.enabled,
              log_paths: row.log?.paths || [],
              slowlog_enabled: !!row.slowlog?.enabled,
              slowlog_hosts: row.slowlog?.hosts || [],
              slowlog_password: row.slowlog?.password || ''
            };

            return {
              collector: pluginConfig.collector,
              collect_type: pluginConfig.collect_type,
              configs: [configData],
              instances: dataSource.map((item: TableDataItem) => {
                return {
                  ...item,
                  node_ids: [item.node_ids].flat()
                };
              })
            };
          }
        },
        edit: {
          getFormItems: () => {
            return commonFormItems.getCommonFormItems({
              disabledFormItems: {},
              hiddenFormItems: {}
            });
          },
          getDefaultForm: (formData: TableDataItem) => {
            const content = formData?.child?.content || [];
            const redisConfig =
              content.find((item: any) => item.module === 'redis') || {};

            return {
              log: {
                enabled: !!redisConfig.log?.enabled,
                paths: redisConfig.log?.['var.paths'] || []
              },
              slowlog: {
                enabled: !!redisConfig.slowlog?.enabled,
                hosts: redisConfig.slowlog?.['var.hosts'] || [],
                password: redisConfig.slowlog?.['var.password'] || ''
              }
            };
          },
          getParams: (formData: TableDataItem, configForm: TableDataItem) => {
            const originalChild = cloneDeep(configForm?.child || {});

            // 扁平化的 content（5个参数，和新增一致）
            const content = {
              log_enabled: !!formData.log?.enabled,
              log_paths: formData.log?.paths || [],
              slowlog_enabled: !!formData.slowlog?.enabled,
              slowlog_hosts: formData.slowlog?.hosts || [],
              slowlog_password: formData.slowlog?.password || ''
            };

            return {
              child: {
                ...originalChild,
                content
              }
            };
          }
        },
        manual: {
          defaultForm: {},
          formItems: commonFormItems.getCommonFormItems(),
          getParams: (row: TableDataItem) => {
            return {
              instance_name: row.instance_name,
              instance_id: row.instance_id
            };
          },
          getConfigText: () => '--'
        }
      };
      return {
        ...pluginConfig,
        ...configs[extra.mode]
      };
    }
  };
};
