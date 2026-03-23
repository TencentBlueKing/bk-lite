import { IntegrationLogInstance } from '@/app/log/types/integration';
import { TableDataItem } from '@/app/log/types';
import { useNginxFilebeatFormItems } from '../../common/nginxFilebeatFormItems';
import { cloneDeep } from 'lodash';

export const useNginxFilebeatConfig = () => {
  const commonFormItems = useNginxFilebeatFormItems();
  const pluginConfig = {
    collector: 'Filebeat',
    collect_type: 'nginx',
    icon: 'nginx'
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
              paths: ['/var/log/nginx/access.log']
            },
            error_log: {
              enabled: true,
              paths: ['/var/log/nginx/error.log']
            },
            ingress_controller: {
              enabled: false,
              paths: []
            }
          },
          columns: [],
          getParams: (row: IntegrationLogInstance, config: TableDataItem) => {
            const dataSource = cloneDeep(config.dataSource || []);

            // Flat structure with 6 fields
            const configData = {
              access_enabled: !!row.access_log?.enabled,
              access_paths: row.access_log?.paths || [],
              error_enabled: !!row.error_log?.enabled,
              error_paths: row.error_log?.paths || [],
              ingress_controller_enabled: !!row.ingress_controller?.enabled,
              ingress_controller_paths: row.ingress_controller?.paths || []
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
            const nginxConfig =
              content.find((item: any) => item.module === 'nginx') || {};

            return {
              access_log: {
                enabled: !!nginxConfig.access?.enabled,
                paths: nginxConfig.access?.['var.paths'] || []
              },
              error_log: {
                enabled: !!nginxConfig.error?.enabled,
                paths: nginxConfig.error?.['var.paths'] || []
              },
              ingress_controller: {
                enabled: !!nginxConfig.ingress_controller?.enabled,
                paths: nginxConfig.ingress_controller?.['var.paths'] || []
              }
            };
          },
          getParams: (formData: TableDataItem, configForm: TableDataItem) => {
            const originalChild = cloneDeep(configForm?.child || {});

            // 扁平化的 content（6个参数，和新增一致）
            const content = {
              access_enabled: !!formData.access_log?.enabled,
              access_paths: formData.access_log?.paths || [],
              error_enabled: !!formData.error_log?.enabled,
              error_paths: formData.error_log?.paths || [],
              ingress_controller_enabled:
                !!formData.ingress_controller?.enabled,
              ingress_controller_paths: formData.ingress_controller?.paths || []
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
