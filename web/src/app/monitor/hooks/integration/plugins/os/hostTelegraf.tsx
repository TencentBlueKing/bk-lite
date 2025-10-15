import React from 'react';
import { Form, Input } from 'antd';
import { useTranslation } from '@/utils/i18n';
import { IntegrationMonitoredObject } from '@/app/monitor/types/integration';
import { TableDataItem } from '@/app/monitor/types';
import { useHostFormItems } from '../../common/hostFormItems';
import { cloneDeep } from 'lodash';
import { replaceTemplate } from '@/app/monitor/utils/integration';

export const useHostTelegraf = () => {
  const { t } = useTranslation();
  const hostFormItems = useHostFormItems();
  const pluginConfig = {
    collect_type: 'host',
    config_type: [
      'cpu',
      'disk',
      'diskio',
      'mem',
      'net',
      'processes',
      'system',
      'gpu',
    ],
    collector: 'Telegraf',
    instance_type: 'os',
    object_name: 'Host',
  };

  return {
    getPluginCfg: (extra: {
      dataSource?: IntegrationMonitoredObject[];
      mode: 'manual' | 'auto' | 'edit';
      onTableDataChange?: (data: IntegrationMonitoredObject[]) => void;
    }) => {
      const formItems = (
        <>
          {hostFormItems.getCommonFormItems(
            extra.mode === 'edit' ? { metric_type: true } : {}
          )}
          <Form.Item required label="IP">
            <Form.Item
              noStyle
              name="monitor_ip"
              rules={[
                {
                  required: true,
                  message: t('common.required'),
                },
              ]}
            >
              <Input
                className="w-[300px] mr-[10px]"
                disabled={extra.mode === 'edit'}
              />
            </Form.Item>
            <span className="text-[12px] text-[var(--color-text-3)]">
              {t('monitor.integrations.ipDes')}
            </span>
          </Form.Item>
        </>
      );

      const config = {
        auto: {
          formItems: hostFormItems.getCommonFormItems(),
          initTableItems: {},
          defaultForm: {
            metric_type: pluginConfig.config_type.filter(
              (item: string) => item !== 'gpu'
            ),
          },
          columns: [],
          getParams: (
            row: IntegrationMonitoredObject,
            config: TableDataItem
          ) => {
            const dataSource = cloneDeep(config.dataSource || []);
            const { metric_type, ...rest } = row;
            return {
              configs: metric_type.map((item: string) => ({
                type: item,
                ...rest,
              })),
              collect_type: pluginConfig.collect_type,
              collector: pluginConfig.collector,
              instances: dataSource.map((item: TableDataItem) => {
                delete item.key;
                const target: TableDataItem | undefined = config.nodeList.find(
                  (tex: IntegrationMonitoredObject) => item.node_ids === tex.id
                );
                return {
                  ...item,
                  node_ids: [item.node_ids].flat(),
                  instance_type: pluginConfig.instance_type,
                  instance_id: target?.ip + '-' + target?.cloud_region,
                };
              }),
            };
          },
        },
        edit: {
          formItems,
          getDefaultForm: (formData: TableDataItem) => {
            const config = formData?.child?.content?.config || {};
            return {
              metric_type: [config.tags?.config_type],
              monitor_ip:
                (config.tags?.instance_id || '').split('-')?.[0] || '',
            };
          },
          getParams: (
            row: IntegrationMonitoredObject,
            config: TableDataItem
          ) => {
            return config;
          },
        },
        manual: {
          defaultForm: {
            metric_type: pluginConfig.config_type.filter(
              (item: string) => item !== 'gpu'
            ),
          },
          formItems,
          getParams: (row: TableDataItem) => {
            const instanceId = row.monitor_ip;
            return {
              instance_id: instanceId,
              instance_name: instanceId,
            };
          },
          getConfigText: (formData: { [key: string]: string | number }) => {
            const configText: Record<string, string> = {
              cpu: `[[inputs.cpu]]
        percpu = true
        totalcpu = true
        collect_cpu_time = false
        report_active = false
        core_tags = false
        interval = "$intervals"
        tags = { "instance_id"="$instance_id","instance_type"="os","collect_type"="host","config_type"="cpu" }
        
    `,
              disk: `[[inputs.disk]]
        ignore_fs = ["tmpfs", "devtmpfs", "devfs", "iso9660", "overlay", "aufs", "squashfs"]
        interval = "$intervals"
        tags = { "instance_id"="$instance_id","instance_type"="os","collect_type"="host","config_type"="disk" }
        
    `,
              diskio: `[[inputs.diskio]]
        interval = "$intervals"
        tags = { "instance_id"="$instance_id","instance_type"="os","collect_type"="host","config_type"="diskio" }
        
    `,
              mem: `[[inputs.mem]]
        interval = "$intervals"
        tags = { "instance_id"="$instance_id","instance_type"="os","collect_type"="host","config_type"="mem" }
        
    `,
              net: `[[inputs.net]]
        interval = "$intervals"
        tags = { "instance_id"="$instance_id","instance_type"="os","collect_type"="host","config_type"="net" }
    
    `,
              processes: `[[inputs.processes]]
        interval = "$intervals"
        tags = { "instance_id"="$instance_id","instance_type"="os","collect_type"="host","config_type"="processes" }
        
    `,
              system: `[[inputs.system]]
        interval = "$intervals"
        tags = { "instance_id"="$instance_id","instance_type"="os","collect_type"="host","config_type"="system" }
        
    `,
              gpu: `[[inputs.nvidia_smi]]
        interval = "$intervals"
        [inputs.docker.tags]
            instance_id = "$instance_id"
            instance_type = "os"
            collect_type = "host"
            config_type = "gpu"
        
    `,
            };
            const instanceId = formData.monitor_ip;
            const metricType: any = formData.metric_type;
            const text = metricType.reduce((pre: string, cur: string) => {
              return (pre += configText[cur]);
            }, '');
            return replaceTemplate(text, {
              ...formData,
              instance_id: instanceId,
              instance_type: pluginConfig.instance_type,
              collect_type: pluginConfig.collect_type,
              config_type: pluginConfig.config_type[0] || '',
            });
          },
        },
      };

      return {
        ...pluginConfig,
        ...config[extra.mode],
      };
    },
  };
};
