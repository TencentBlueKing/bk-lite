import { IntegrationLogInstance } from '@/app/log/types/integration';
import { TableDataItem } from '@/app/log/types';
import { useDockerVectorFormItems } from '../../common/dockerVectorFormItems';
import { cloneDeep } from 'lodash';

export const useVectorConfig = () => {
  const commonFormItems = useDockerVectorFormItems();
  const pluginConfig = {
    collector: 'Vector',
    collect_type: 'docker',
    icon: 'docker-run-to-docker-compose'
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
            hiddenFormItems: {},
            disabledFormItems: {}
          }),
          initTableItems: {},
          defaultForm: {
            endpoint: 'unix:///var/run/docker.sock',
            containerFilter: {
              enabled: false
            },
            container_name_contains: [],
            container_name_exclude: ['vector', 'logspout'],
            multiline: {
              enabled: false,
              mode: 'continue_through',
              condition_pattern: '^[\\s]+',
              start_pattern: '^[^\\s]',
              timeout_ms: 1000
            }
          },
          columns: [],
          getParams: (row: IntegrationLogInstance, config: TableDataItem) => {
            const dataSource = cloneDeep(config.dataSource || []);
            const formData = cloneDeep(row);

            // 处理容器过滤开关
            const enableContainerFilter =
              formData.containerFilter?.enabled || false;
            delete formData.containerFilter;

            // 处理多行合并开关
            const enableMultiline = formData.multiline?.enabled || false;
            delete formData.multiline?.enabled;

            // 构建最终参数
            const params: any = {
              endpoint: formData.endpoint,
              enable_container_filter: enableContainerFilter,
              enable_multiline: enableMultiline
            };

            // 容器过滤参数
            if (enableContainerFilter) {
              const containsArr = formData.container_name_contains || [];
              const excludeArr = formData.container_name_exclude || [];
              params.container_name_contains = Array.isArray(containsArr)
                ? containsArr.join(',')
                : containsArr;
              params.container_name_exclude = Array.isArray(excludeArr)
                ? excludeArr.join(',')
                : excludeArr;
            }

            // 多行合并参数
            if (enableMultiline) {
              params.multiline_mode =
                formData.multiline?.mode || 'continue_through';
              params.multiline_pattern =
                formData.multiline?.condition_pattern || '^[\\s]+';
              params.multiline_start_pattern =
                formData.multiline?.start_pattern || '^[^\\s]';
              params.multiline_timeout_ms =
                formData.multiline?.timeout_ms || 1000;
            }

            return {
              collector: pluginConfig.collector,
              collect_type: pluginConfig.collect_type,
              configs: [params],
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
              hiddenFormItems: {},
              disabledFormItems: {}
            });
          },
          getDefaultForm: (formData: TableDataItem) => {
            const sources =
              formData?.child?.content?.sources?.[
                pluginConfig.collect_type + '_' + formData.rowId
              ] || {};

            // 从实际数据结构中获取容器过滤数组
            const includeContainers = sources.include_containers || [];
            const excludeContainers = sources.exclude_containers || [];

            // 判断容器过滤是否开启：有 include 或 exclude 数组且不为空
            const hasContainerFilter =
              includeContainers.length > 0 || excludeContainers.length > 0;

            return {
              endpoint: sources.docker_host || 'unix:///var/run/docker.sock',
              containerFilter: {
                enabled: hasContainerFilter
              },
              container_name_contains: includeContainers,
              container_name_exclude: excludeContainers,
              multiline: {
                enabled: !!sources.multiline?.mode,
                mode: sources.multiline?.mode || 'continue_through',
                condition_pattern:
                  sources.multiline?.condition_pattern || '^[\\s]+',
                start_pattern: sources.multiline?.start_pattern || '^[^\\s]',
                timeout_ms: sources.multiline?.timeout_ms || 1000
              }
            };
          },
          getParams: (formData: TableDataItem, configForm: TableDataItem) => {
            const originalChild = cloneDeep(configForm?.child || {});
            const formDataCopy = cloneDeep(formData);

            // 处理容器过滤开关
            const enableContainerFilter =
              formDataCopy.containerFilter?.enabled || false;

            // 处理多行合并开关
            const enableMultiline = formDataCopy.multiline?.enabled || false;

            // 容器过滤参数
            const containsArr = formDataCopy.container_name_contains || [];
            const excludeArr = formDataCopy.container_name_exclude || [];

            // 构建扁平化的 content 对象（9个参数）
            const content: any = {
              endpoint: formDataCopy.endpoint,
              enable_container_filter: enableContainerFilter,
              container_name_contains: Array.isArray(containsArr)
                ? containsArr.join(',')
                : containsArr,
              container_name_exclude: Array.isArray(excludeArr)
                ? excludeArr.join(',')
                : excludeArr,
              enable_multiline: enableMultiline,
              multiline_mode:
                formDataCopy.multiline?.mode || 'continue_through',
              multiline_pattern:
                formDataCopy.multiline?.condition_pattern || '^[\\s]+',
              multiline_start_pattern:
                formDataCopy.multiline?.start_pattern || '^[^\\s]',
              multiline_timeout_ms: formDataCopy.multiline?.timeout_ms || 1000
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
          formItems: commonFormItems.getCommonFormItems({
            hiddenFormItems: {},
            disabledFormItems: {}
          }),
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
