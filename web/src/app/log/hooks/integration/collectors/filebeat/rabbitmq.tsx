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
            const originalChild = cloneDeep(configForm?.child || {});

            // 扁平化的 content（2个参数，和新增一致）
            const content = {
              log_enabled: !!formData.log?.enabled,
              log_paths: formData.log?.paths || []
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
