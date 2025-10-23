import React from 'react';
import { IntegrationLogInstance } from '@/app/log/types/integration';
import { TableDataItem } from '@/app/log/types';
import { useSystemMetricbeatFormItems } from '../../common/systemMetricbeatFormItems';
import { cloneDeep } from 'lodash';
import { v4 as uuidv4 } from 'uuid';

export const useMetricbeatConfig = () => {
  const commonFormItems = useSystemMetricbeatFormItems();
  const pluginConfig = {
    collector: 'Metricbeat',
    collect_type: 'system',
    icon: 'zhibiao',
  };

  return {
    getConfig: (extra: {
      dataSource?: IntegrationLogInstance[];
      mode: 'manual' | 'auto' | 'edit';
      onTableDataChange?: (data: IntegrationLogInstance[]) => void;
    }) => {
      const formItems = <>{commonFormItems.getCommonFormItems()}</>;
      const configs = {
        auto: {
          formItems: commonFormItems.getCommonFormItems({
            disabledFormItems: {},
            mode: extra.mode,
          }),
          initTableItems: {
            instance_id: `${pluginConfig.collector}-${
              pluginConfig.collect_type
            }-${uuidv4()}`,
          },
          defaultForm: {
            metricsets: [
              'cpu',
              'load',
              'memory',
              'network',
              'process',
              'process_summary',
              'uptime',
              'socket_summary',
            ],
          },
          columns: [],
          getParams: (row: IntegrationLogInstance, config: TableDataItem) => {
            const dataSource = cloneDeep(config.dataSource || []);
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
            const metricsets =
              formData?.child?.content?.[0]?.metricsets || null;
            return {
              metricsets,
            };
          },
          getParams: (formData: TableDataItem, configForm: TableDataItem) => {
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
