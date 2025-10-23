import React from 'react';
import { IntegrationLogInstance } from '@/app/log/types/integration';
import { TableDataItem } from '@/app/log/types';
import { useFileVectorFormItems } from '../../common/fileVectorFormItems';
import { cloneDeep } from 'lodash';

export const useVectorConfig = () => {
  const commonFormItems = useFileVectorFormItems();
  const pluginConfig = {
    collector: 'Vector',
    collect_type: 'file',
    icon: 'jiaoxuerizhiPC',
  };

  return {
    getConfig: (extra: {
      dataSource?: IntegrationLogInstance[];
      mode: 'manual' | 'auto' | 'edit';
      onTableDataChange?: (data: IntegrationLogInstance[]) => void;
    }) => {
      const disabledForm = {
        file_path: false,
      };
      const formItems = <>{commonFormItems.getCommonFormItems(disabledForm)}</>;
      const configs = {
        auto: {
          formItems: commonFormItems.getCommonFormItems(),
          initTableItems: {},
          defaultForm: {
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
          formItems,
          getDefaultForm: (formData: TableDataItem) => {
            const sources =
              formData?.child?.content?.sources?.[
                pluginConfig.collect_type + '_' + formData.rowId
              ];
            const path = sources?.include?.[0] || null;
            return {
              file_path: path,
              multiline: Object.assign(sources?.multiline || {}, {
                enabled: !!sources?.multiline?.mode,
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
          formItems,
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
