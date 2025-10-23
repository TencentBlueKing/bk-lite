import { IntegrationLogInstance } from '@/app/log/types/integration';
import { TableDataItem } from '@/app/log/types';
import { useDockerVectorFormItems } from '../../common/dockerVectorFormItems';
import { cloneDeep } from 'lodash';

export const useVectorConfig = () => {
  const commonFormItems = useDockerVectorFormItems();
  const pluginConfig = {
    collector: 'Vector',
    collect_type: 'docker',
    icon: 'docker-run-to-docker-compose',
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
            hiddenFormItems: {
              start_pattern: true,
            },
            disabledFormItems: {},
          }),
          initTableItems: {},
          defaultForm: {
            docker_host: 'unix:///var/run/docker.sock',
            multiline: {
              enabled: true,
              mode: 'continue_through',
              start_pattern: '^(ERROR|WARN|INFO|DEBUG|TRACE|FATAL)\\s\\[',
              timeout_ms: 3000,
              condition_pattern: '^(\\s+|Traceback|File\\s+)',
            },
          },
          columns: [],
          getParams: (row: IntegrationLogInstance, config: TableDataItem) => {
            const dataSource = cloneDeep(config.dataSource || []);
            delete row.multiline.enabled;
            return {
              collector: pluginConfig.collector,
              collect_type: pluginConfig.collect_type,
              configs: [row],
              instances: dataSource.map((item: TableDataItem) => {
                return {
                  ...item,
                  node_ids: [item.node_ids].flat(),
                };
              }),
            };
          },
        },
        edit: {
          getFormItems: () => {
            return commonFormItems.getCommonFormItems({
              hiddenFormItems: {
                start_pattern: true,
              },
              disabledFormItems: {},
            });
          },
          getDefaultForm: (formData: TableDataItem) => {
            const sources =
              formData?.child?.content?.sources?.[
                pluginConfig.collect_type + '_' + formData.rowId
              ] || {};
            const multiline = sources.multiline || {};
            return {
              docker_host: sources.docker_host || null,
              include_containers: sources.include_containers || null,
              exclude_containers: sources.exclude_containers || null,
              multiline: Object.assign(multiline, {
                enabled: !!multiline.mode,
              }),
            };
          },
          getParams: (formData: TableDataItem, configForm: TableDataItem) => {
            delete formData.multiline.enabled;
            return {
              child: {
                id: configForm.child.id,
                content_data: formData,
              },
            };
          },
        },
        manual: {
          defaultForm: {},
          formItems: commonFormItems.getCommonFormItems(),
          getParams: (row: TableDataItem) => {
            return {
              instance_name: row.instance_name,
              instance_id: row.instance_id,
            };
          },
          getConfigText: () => '--',
        },
      };
      return {
        ...pluginConfig,
        ...configs[extra.mode],
      };
    },
  };
};
