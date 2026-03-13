import { IntegrationLogInstance } from '@/app/log/types/integration';
import { TableDataItem } from '@/app/log/types';
import { usePostgresqlFilebeatFormItems } from '../../common/postgresqlFilebeatFormItems';
import { cloneDeep } from 'lodash';

export const usePostgresqlFilebeatConfig = () => {
  const commonFormItems = usePostgresqlFilebeatFormItems();
  const pluginConfig = {
    collector: 'Filebeat',
    collect_type: 'postgresql',
    icon: 'postgresql'
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
              paths: ['/var/log/postgresql/postgresql-14-main.log']
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
            const content = formData?.child?.content || [];
            const postgresqlConfig =
              content.find((item: any) => item.module === 'postgresql') || {};

            return {
              log: {
                enabled: !!postgresqlConfig.log?.enabled,
                paths: postgresqlConfig.log?.['var.paths'] || []
              }
            };
          },
          getParams: (formData: TableDataItem, configForm: TableDataItem) => {
            const originalChild = cloneDeep(configForm?.child || {});
            const updatedContent = (originalChild.content || []).map(
              (item: any) => {
                if (item.module === 'postgresql') {
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
