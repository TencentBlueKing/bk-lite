import React from 'react';
import { IntegrationLogInstance } from '@/app/log/types/integration';
import { TableDataItem } from '@/app/log/types';
import { useFilestreamFilebeatFormItems } from '../../common/filestreamFilebeatFormItems';
import { cloneDeep } from 'lodash';

export const useFilebeatConfig = () => {
  const commonFormItems = useFilestreamFilebeatFormItems();
  const pluginConfig = {
    collector: 'Filebeat',
    collect_type: 'filestream',
    icon: 'rizhi3',
  };

  return {
    getConfig: (extra: {
      dataSource?: IntegrationLogInstance[];
      mode: 'manual' | 'auto' | 'edit';
      onTableDataChange?: (data: IntegrationLogInstance[]) => void;
    }) => {
      const formItems = (
        <>
          {commonFormItems.getCommonFormItems({
            hiddenFormItems: {},
            disabledFormItems: {},
          })}
        </>
      );
      const configs = {
        auto: {
          formItems: commonFormItems.getCommonFormItems(),
          initTableItems: {},
          defaultForm: {
            multiline: {
              enabled: true,
              negate: false,
              pattern: '^\\d{4}-\\d{2}-\\d{2}',
              timeout: 5,
              match: 'after',
              max_lines: 500,
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
            const sources = formData?.child?.content?.[0] || {};
            const multiline = sources?.parsers?.[0]?.multiline || {};
            const configForm: Record<string, string | boolean> = {
              enabled: !!multiline.type,
            };
            if (multiline.timeout) {
              configForm.timeout = multiline.timeout.replace('s', '');
            }
            return {
              paths: sources.paths,
              multiline: Object.assign(multiline, configForm),
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
