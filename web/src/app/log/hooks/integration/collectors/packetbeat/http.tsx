import React from 'react';
import { IntegrationLogInstance } from '@/app/log/types/integration';
import { TableDataItem } from '@/app/log/types';
import { useHttpPacketbeatFormItems } from '../../common/httpPacketbeatFormItems';
import { cloneDeep } from 'lodash';
import { v4 as uuidv4 } from 'uuid';

export const usePacketbeatConfig = () => {
  const commonFormItems = useHttpPacketbeatFormItems();
  const pluginConfig = {
    collector: 'Packetbeat',
    collect_type: 'http',
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
            ports: [80, 8080, 8000, 5000, 8002],
            capture_body: false
          },
          columns: [],
          getParams: (row: IntegrationLogInstance, config: TableDataItem) => {
            const dataSource = cloneDeep(config.dataSource || []);
            // 将 ports 数组转换为逗号分隔的字符串
            const ports = Array.isArray(row.ports)
              ? row.ports.join(',')
              : row.ports;
            return {
              collector: pluginConfig.collector,
              collect_type: pluginConfig.collect_type,
              configs: [
                {
                  ...row,
                  ports,
                  capture_body: row.capture_body || false
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
            const content = formData?.child?.content;
            // 后端返回的结构是 content 数组，取第一个元素
            const httpConfig = Array.isArray(content)
              ? content[0]
              : content || {};
            // 处理 ports 回显
            let ports = httpConfig?.ports;
            if (typeof ports === 'string') {
              ports = ports.split(',').filter(Boolean);
            }
            // capture_body 回显：后端用 include_request_body 或 include_response_body
            const captureBody =
              httpConfig?.include_request_body ||
              httpConfig?.include_response_body ||
              false;
            return {
              ports: ports || null,
              capture_body: captureBody
            };
          },
          getParams: (formData: TableDataItem, configForm: TableDataItem) => {
            const originalChild = cloneDeep(configForm?.child || {});
            // 将 ports 数组转换为逗号分隔的字符串
            const ports = Array.isArray(formData.ports)
              ? formData.ports.join(',')
              : formData.ports;
            return {
              child: {
                ...originalChild,
                content: {
                  ports,
                  capture_body: formData.capture_body || false
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
