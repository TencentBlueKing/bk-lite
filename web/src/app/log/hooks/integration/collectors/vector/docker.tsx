import { IntegrationLogInstance } from '@/app/log/types/integration';
import { TableDataItem } from '@/app/log/types';
import { useDockerVectorFormItems } from '../../common/dockerVectorFormItems';
import {
  getVectorDockerDefaultForm,
  getVectorDockerParams
} from './dockerDefaults';

export const useVectorConfig = () => {
  const commonFormItems = useDockerVectorFormItems();
  const pluginConfig = {
    collector: 'Vector',
    collect_type: 'docker',
    icon: 'mm-docker_Docker'
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
            // auto 模式保留旧实现：构造 configs: [params] 数组项，与 edit 不同。
            const dataSource = config.dataSource || [];
            const formData = { ...row };

            // 处理容器过滤开关
            const enableContainerFilter =
              formData.containerFilter?.enabled || false;

            // 处理多行合并开关
            const enableMultiline = formData.multiline?.enabled || false;

            // 构建最终参数
            const params: Record<string, unknown> = {
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
          // 从 ./dockerDefaults 导入的纯函数 —— 与 getVectorDockerParams 写入结构一致
          getDefaultForm: getVectorDockerDefaultForm,
          getParams: getVectorDockerParams
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