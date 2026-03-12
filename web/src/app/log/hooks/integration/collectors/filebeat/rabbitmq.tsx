import { IntegrationLogInstance } from '@/app/log/types/integration';
import { TableDataItem } from '@/app/log/types';
import { useRabbitmqFilebeatFormItems } from '../../common/rabbitmqFilebeatFormItems';
import { cloneDeep } from 'lodash';

export const useRabbitmqFilebeatConfig = () => {
  const commonFormItems = useRabbitmqFilebeatFormItems();
  const pluginConfig = {
    collector: 'Filebeat',
    collect_type: 'rabbitmq',
    icon: 'rabbitmq'
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
              paths: ['/var/log/rabbitmq/rabbit@hostname.log']
            }
          },
          columns: [],
          getParams: (row: IntegrationLogInstance, config: TableDataItem) => {
            const dataSource = cloneDeep(config.dataSource || []);

            // Flat structure with 2 fields: log_enabled, log_paths
            const configData = {
              log_enabled: !!row.log?.enabled,
              log_paths: row.log?.paths || []
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
            // 从 content 数组中获取配置数据
            const content = formData?.child?.content || [];
            const logConfig =
              content.find((item: any) => item.module === 'rabbitmq') || {};

            return {
              log: {
                enabled: !!logConfig.log?.enabled,
                paths: logConfig.log?.['var.paths'] || []
              }
            };
          },
          getParams: (formData: TableDataItem, configForm: TableDataItem) => {
            // 深拷贝原始 child 对象，保持完整结构
            const originalChild = cloneDeep(configForm?.child || {});

            // 更新 content 中 rabbitmq 模块的 log 配置
            const updatedContent = (originalChild.content || []).map(
              (item: any) => {
                if (item.module === 'rabbitmq') {
                  return {
                    ...item,
                    log: {
                      ...item.log,
                      enabled: !!formData.log?.enabled,
                      'var.paths': formData.log?.paths || []
                    }
                  };
                }
                return item;
              }
            );

            return {
              child: {
                ...originalChild,
                content: updatedContent
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
