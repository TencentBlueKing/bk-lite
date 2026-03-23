import { IntegrationLogInstance } from '@/app/log/types/integration';
import { TableDataItem } from '@/app/log/types';
import { useApacheFilebeatFormItems } from '../../common/apacheFilebeatFormItems';
import { cloneDeep } from 'lodash';

export const useFilebeatConfig = () => {
  const commonFormItems = useApacheFilebeatFormItems();
  const pluginConfig = {
    collector: 'Filebeat',
    collect_type: 'apache',
    icon: 'apache'
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
            access_log: {
              enabled: true,
              paths: ['/var/log/apache2/access.log']
            },
            error_log: {
              enabled: true,
              paths: ['/var/log/apache2/error.log']
            }
          },
          columns: [],
          getParams: (row: IntegrationLogInstance, config: TableDataItem) => {
            const dataSource = cloneDeep(config.dataSource || []);

            // Flat structure with 4 fields: access_enabled, access_paths, error_enabled, error_paths
            const configData = {
              access_enabled: !!row.access_log?.enabled,
              access_paths: row.access_log?.paths || [],
              error_enabled: !!row.error_log?.enabled,
              error_paths: row.error_log?.paths || []
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
            const apacheConfig =
              content.find((item: any) => item.module === 'apache') || {};

            return {
              access_log: {
                enabled: !!apacheConfig.access?.enabled,
                paths: apacheConfig.access?.['var.paths'] || []
              },
              error_log: {
                enabled: !!apacheConfig.error?.enabled,
                paths: apacheConfig.error?.['var.paths'] || []
              }
            };
          },
          getParams: (formData: TableDataItem, configForm: TableDataItem) => {
            const originalChild = cloneDeep(configForm?.child || {});

            // 扁平化的 content（4个参数，和新增一致）
            const content = {
              access_enabled: !!formData.access_log?.enabled,
              access_paths: formData.access_log?.paths || [],
              error_enabled: !!formData.error_log?.enabled,
              error_paths: formData.error_log?.paths || []
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
