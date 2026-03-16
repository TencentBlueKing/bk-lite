import React from 'react';
import { IntegrationLogInstance } from '@/app/log/types/integration';
import { TableDataItem } from '@/app/log/types';
import { useFlowsPacketbeatFormItems } from '../../common/flowsPacketbeatFormItems';
import { cloneDeep } from 'lodash';
import { v4 as uuidv4 } from 'uuid';

// 解析带单位的值，如 "10s" 或 "10ss" → 10
const parseValueWithUnit = (
  value: string | number | null | undefined
): number | null => {
  if (value === null || value === undefined) return null;
  if (typeof value === 'number') return value;
  const match = String(value).match(/^(\d+)/);
  return match ? parseInt(match[1], 10) : null;
};

export const usePacketbeatConfig = () => {
  const commonFormItems = useFlowsPacketbeatFormItems();
  const pluginConfig = {
    collector: 'Packetbeat',
    collect_type: 'flows',
    icon: 'wangluo'
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
            disabledFormItems: {}
          })}
        </>
      );
      const configs = {
        auto: {
          formItems: commonFormItems.getCommonFormItems(),
          initTableItems: {
            instance_id: `${pluginConfig.collector}-${
              pluginConfig.collect_type
            }-${uuidv4()}`
          },
          defaultForm: {
            flows_period: 10,
            flows_timeout: 30
          },
          columns: [],
          getParams: (row: IntegrationLogInstance, config: TableDataItem) => {
            const dataSource = cloneDeep(config.dataSource || []);
            return {
              collector: pluginConfig.collector,
              collect_type: pluginConfig.collect_type,
              configs: [
                {
                  ...row,
                  flows_period: row.flows_period || 10,
                  flows_timeout: row.flows_timeout || 30
                }
              ],
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
          formItems,
          getDefaultForm: (formData: TableDataItem) => {
            const content = formData?.child?.content || {};
            // 后端返回的结构是 content['packetbeat.flows']
            const flowsConfig = content['packetbeat.flows'] || {};
            const flowsPeriod = flowsConfig?.period || null;
            const flowsTimeout = flowsConfig?.timeout || null;
            return {
              flows_period: parseValueWithUnit(flowsPeriod),
              flows_timeout: parseValueWithUnit(flowsTimeout)
            };
          },
          getParams: (formData: TableDataItem, configForm: TableDataItem) => {
            const originalChild = cloneDeep(configForm?.child || {});
            return {
              child: {
                ...originalChild,
                content: {
                  flows_period: formData.flows_period || 10,
                  flows_timeout: formData.flows_timeout || 30
                }
              }
            };
          }
        },
        manual: {
          defaultForm: {},
          formItems,
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
