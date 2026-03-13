import { IntegrationLogInstance } from '@/app/log/types/integration';
import { TableDataItem } from '@/app/log/types';
import { useMysqlFilebeatFormItems } from '../../common/mysqlFilebeatFormItems';
import { cloneDeep } from 'lodash';

export const useMysqlFilebeatConfig = () => {
  const commonFormItems = useMysqlFilebeatFormItems();
  const pluginConfig = {
    collector: 'Filebeat',
    collect_type: 'mysql',
    icon: 'mysql'
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
            error_log: {
              enabled: true,
              paths: ['/var/log/mysql/error.log']
            },
            slowlog: {
              enabled: false,
              paths: []
            }
          },
          columns: [],
          getParams: (row: IntegrationLogInstance, config: TableDataItem) => {
            const dataSource = cloneDeep(config.dataSource || []);

            // Flat structure with 4 fields
            const configData = {
              error_enabled: !!row.error_log?.enabled,
              error_paths: row.error_log?.paths || [],
              slowlog_enabled: !!row.slowlog?.enabled,
              slowlog_paths: row.slowlog?.paths || []
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
            const mysqlConfig =
              content.find((item: any) => item.module === 'mysql') || {};

            return {
              error_log: {
                enabled: !!mysqlConfig.error?.enabled,
                paths: mysqlConfig.error?.['var.paths'] || []
              },
              slowlog: {
                enabled: !!mysqlConfig.slowlog?.enabled,
                paths: mysqlConfig.slowlog?.['var.paths'] || []
              }
            };
          },
          getParams: (formData: TableDataItem, configForm: TableDataItem) => {
            const originalChild = cloneDeep(configForm?.child || {});

            // 扁平化的 content（4个参数，和新增一致）
            const content = {
              error_enabled: !!formData.error_log?.enabled,
              error_paths: formData.error_log?.paths || [],
              slowlog_enabled: !!formData.slowlog?.enabled,
              slowlog_paths: formData.slowlog?.paths || []
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
