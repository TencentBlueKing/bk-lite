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

const DEFAULT_HTTP_PORTS = [80, 8080, 8000, 5000, 8002];
const DEFAULT_DEVICE = 'any';
const DEFAULT_FLOWS_PERIOD = 10;
const DEFAULT_FLOWS_TIMEOUT = 30;

const normalizePorts = (ports: unknown) =>
  Array.isArray(ports) ? ports.join(',') : ports;

const getHttpConfig = (content: any) => {
  const protocols = content?.['packetbeat.protocols'];
  if (!Array.isArray(protocols)) return {};
  return protocols.find((item) => item?.type === 'http') || {};
};

export const usePacketbeatConfig = () => {
  const commonFormItems = useFlowsPacketbeatFormItems();
  const pluginConfig = {
    collector: 'Packetbeat',
    collect_type: 'flows',
    icon: 'll-flows_网络流量'
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
            device: DEFAULT_DEVICE,
            enable_http: true,
            enable_tcp_udp: true,
            ports: DEFAULT_HTTP_PORTS,
            capture_body: false,
            flows_period: DEFAULT_FLOWS_PERIOD,
            flows_timeout: DEFAULT_FLOWS_TIMEOUT
          },
          columns: [],
          getParams: (row: IntegrationLogInstance, config: TableDataItem) => {
            const dataSource = cloneDeep(config.dataSource || []);
            if (!row.enable_http && !row.enable_tcp_udp) {
              throw new Error('网络流量采集至少开启 HTTP 或 TCP/UDP');
            }
            const ports = normalizePorts(row.ports);
            return {
              collector: pluginConfig.collector,
              collect_type: pluginConfig.collect_type,
              configs: [
                {
                  ...row,
                  device: row.device || DEFAULT_DEVICE,
                  enable_http: row.enable_http ?? true,
                  enable_tcp_udp: row.enable_tcp_udp ?? true,
                  ports,
                  capture_body: row.capture_body || false,
                  flows_period: row.flows_period || DEFAULT_FLOWS_PERIOD,
                  flows_timeout: row.flows_timeout || DEFAULT_FLOWS_TIMEOUT
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
            const flowsConfig = content['packetbeat.flows'] || {};
            const httpConfig = getHttpConfig(content);
            const flowsPeriod = flowsConfig?.period || null;
            const flowsTimeout = flowsConfig?.timeout || null;
            const hasHttpConfig = Boolean(httpConfig?.type);
            const hasFlowsConfig = Boolean(content['packetbeat.flows']);
            return {
              device:
                formData?.child?.env_config?.PACKETBEAT_DEVICE_INPUT ||
                formData?.child?.env_config?.PACKETBEAT_DEVICE ||
                formData?.base?.env_config?.PACKETBEAT_DEVICE_INPUT ||
                formData?.base?.env_config?.PACKETBEAT_DEVICE ||
                DEFAULT_DEVICE,
              enable_http: hasHttpConfig || !content['packetbeat.protocols'],
              enable_tcp_udp: hasFlowsConfig || !content['packetbeat.protocols'],
              ports: httpConfig?.ports || DEFAULT_HTTP_PORTS,
              capture_body:
                httpConfig?.include_request_body ||
                httpConfig?.include_response_body ||
                false,
              flows_period:
                parseValueWithUnit(flowsPeriod) || DEFAULT_FLOWS_PERIOD,
              flows_timeout:
                parseValueWithUnit(flowsTimeout) || DEFAULT_FLOWS_TIMEOUT
            };
          },
          getParams: (formData: TableDataItem, configForm: TableDataItem) => {
            const originalChild = cloneDeep(configForm?.child || {});
            if (!formData.enable_http && !formData.enable_tcp_udp) {
              throw new Error('网络流量采集至少开启 HTTP 或 TCP/UDP');
            }
            const ports = normalizePorts(formData.ports);
            return {
              child: {
                ...originalChild,
                env_config: {
                  ...(originalChild.env_config || {}),
                  PACKETBEAT_DEVICE_INPUT: formData.device || DEFAULT_DEVICE,
                  PACKETBEAT_DEVICE: formData.device || DEFAULT_DEVICE
                },
                content: {
                  device: formData.device || DEFAULT_DEVICE,
                  enable_http: formData.enable_http ?? true,
                  enable_tcp_udp: formData.enable_tcp_udp ?? true,
                  ports,
                  capture_body: formData.capture_body || false,
                  flows_period:
                    formData.flows_period || DEFAULT_FLOWS_PERIOD,
                  flows_timeout:
                    formData.flows_timeout || DEFAULT_FLOWS_TIMEOUT
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
