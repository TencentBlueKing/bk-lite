import React from 'react';
import { Form, Input } from 'antd';
import { useTranslation } from '@/utils/i18n';
import { IntegrationMonitoredObject } from '@/app/monitor/types/integration';
import { TableDataItem } from '@/app/monitor/types';
import { cloneDeep } from 'lodash';
import { replaceTemplate } from '@/app/monitor/utils/integration';

export const usePingTelegraf = () => {
  const { t } = useTranslation();
  const pluginConfig = {
    collect_type: 'trap',
    config_type: ['snmp_trap'],
    collector: 'Telegraf',
    instance_type: 'snmp_trap',
    object_name: 'SNMP Trap',
  };

  return {
    getPluginCfg: (extra: {
      dataSource?: IntegrationMonitoredObject[];
      mode: 'manual' | 'auto' | 'edit';
      onTableDataChange?: (data: IntegrationMonitoredObject[]) => void;
    }) => {
      const formItems = (
        <>
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
          formItems: null,
          initTableItems: {},
          defaultForm: {},
          columns: [],
          getParams: (
            row: IntegrationMonitoredObject,
            config: TableDataItem
          ) => {
            const dataSource = cloneDeep(config.dataSource || []);
            return {
              configs: [
                {
                  type: pluginConfig.config_type[0],
                  ...row,
                },
              ],
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
                  instance_id: 'trap' + target?.ip + '-' + target?.cloud_region,
                };
              }),
            };
          },
        },
        edit: {
          formItems,
          getDefaultForm: (formData: TableDataItem) => {
            const url =
              (formData?.child?.content?.config?.tags?.instance_id || '')
                .split('-')?.[0]
                ?.replace('trap', '') || '';
            return {
              monitor_ip: url,
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
          defaultForm: {},
          formItems,
          getParams: (row: TableDataItem) => {
            const instanceId = 'trap' + row.monitor_ip;
            return {
              instance_id: instanceId,
              instance_name: instanceId,
            };
          },
          getConfigText: (formData: { [key: string]: string | number }) => {
            const configText = `[[inputs.$config_type]]
          interval = "$intervals"
          tags = { "instance_id"="$instance_id", "instance_type"="$instance_type", "collect_type"="$collect_type" }`;
            const instanceId = formData.monitor_ip;
            return replaceTemplate(configText, {
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
