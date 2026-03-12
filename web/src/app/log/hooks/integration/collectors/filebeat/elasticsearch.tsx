import { IntegrationLogInstance } from '@/app/log/types/integration';
import { TableDataItem } from '@/app/log/types';
import { useElasticsearchFilebeatFormItems } from '../../common/elasticsearchFilebeatFormItems';
import { cloneDeep } from 'lodash';

export const useElasticsearchFilebeatConfig = () => {
  const commonFormItems = useElasticsearchFilebeatFormItems();
  const pluginConfig = {
    collector: 'Filebeat',
    collect_type: 'elasticsearch',
    icon: 'elasticsearch'
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
            server: {
              enabled: true,
              paths: ['/var/log/elasticsearch/*_server.json']
            },
            gc: {
              enabled: false,
              paths: []
            },
            audit: {
              enabled: false,
              paths: []
            },
            slowlog: {
              enabled: false,
              paths: []
            },
            deprecation: {
              enabled: false,
              paths: []
            }
          },
          columns: [],
          getParams: (row: IntegrationLogInstance, config: TableDataItem) => {
            const dataSource = cloneDeep(config.dataSource || []);

            const configData = {
              server_enabled: !!row.server?.enabled,
              server_paths: row.server?.paths || [],
              gc_enabled: !!row.gc?.enabled,
              gc_paths: row.gc?.paths || [],
              audit_enabled: !!row.audit?.enabled,
              audit_paths: row.audit?.paths || [],
              slowlog_enabled: !!row.slowlog?.enabled,
              slowlog_paths: row.slowlog?.paths || [],
              deprecation_enabled: !!row.deprecation?.enabled,
              deprecation_paths: row.deprecation?.paths || []
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
            const esConfig =
              content.find((item: any) => item.module === 'elasticsearch') ||
              {};

            return {
              server: {
                enabled: !!esConfig.server?.enabled,
                paths: esConfig.server?.['var.paths'] || []
              },
              gc: {
                enabled: !!esConfig.gc?.enabled,
                paths: esConfig.gc?.['var.paths'] || []
              },
              audit: {
                enabled: !!esConfig.audit?.enabled,
                paths: esConfig.audit?.['var.paths'] || []
              },
              slowlog: {
                enabled: !!esConfig.slowlog?.enabled,
                paths: esConfig.slowlog?.['var.paths'] || []
              },
              deprecation: {
                enabled: !!esConfig.deprecation?.enabled,
                paths: esConfig.deprecation?.['var.paths'] || []
              }
            };
          },
          getParams: (formData: TableDataItem, configForm: TableDataItem) => {
            const originalChild = cloneDeep(configForm?.child || {});
            const updatedContent = (originalChild.content || []).map(
              (item: any) => {
                if (item.module === 'elasticsearch') {
                  return {
                    ...item,
                    server: {
                      ...item.server,
                      enabled: !!formData.server?.enabled,
                      'var.paths': formData.server?.paths || []
                    },
                    gc: {
                      ...item.gc,
                      enabled: !!formData.gc?.enabled,
                      'var.paths': formData.gc?.paths || []
                    },
                    audit: {
                      ...item.audit,
                      enabled: !!formData.audit?.enabled,
                      'var.paths': formData.audit?.paths || []
                    },
                    slowlog: {
                      ...item.slowlog,
                      enabled: !!formData.slowlog?.enabled,
                      'var.paths': formData.slowlog?.paths || []
                    },
                    deprecation: {
                      ...item.deprecation,
                      enabled: !!formData.deprecation?.enabled,
                      'var.paths': formData.deprecation?.paths || []
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
