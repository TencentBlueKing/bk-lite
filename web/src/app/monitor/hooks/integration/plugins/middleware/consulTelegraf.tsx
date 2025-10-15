import React from 'react';
import { Form, Input } from 'antd';
import { useTranslation } from '@/utils/i18n';
import {
  InstNameConfig,
  IntegrationMonitoredObject,
} from '@/app/monitor/types/integration';
import { TableDataItem } from '@/app/monitor/types';
import { cloneDeep } from 'lodash';
import { replaceTemplate } from '@/app/monitor/utils/integration';

export const useConsulTelegraf = () => {
  const { t } = useTranslation();
  const pluginConfig = {
    collect_type: 'middleware',
    config_type: ['consul'],
    collector: 'Telegraf',
    instance_type: 'consul',
    object_name: 'Consul',
  };

  return {
    getPluginCfg: (extra: {
      dataSource?: IntegrationMonitoredObject[];
      mode: 'manual' | 'auto' | 'edit';
      onTableDataChange?: (data: IntegrationMonitoredObject[]) => void;
    }) => {
      const handleFieldAndInstNameChange = (
        e: React.ChangeEvent<HTMLInputElement>,
        config: InstNameConfig
      ) => {
        const _dataSource = cloneDeep(extra.dataSource || []);
        _dataSource[config.index][config.field] = _dataSource[
          config.index
        ].instance_name = e.target.value;
        extra.onTableDataChange?.(_dataSource);
      };

      const formItems = (
        <>
          <Form.Item required label={t('monitor.integrations.url')}>
            <Form.Item
              noStyle
              name="monitor_url"
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
              {t('monitor.integrations.urlDes')}
            </span>
          </Form.Item>
        </>
      );

      const config = {
        auto: {
          formItems: null,
          initTableItems: {
            url: null,
          },
          defaultForm: {},
          columns: [
            {
              title: t('monitor.integrations.url'),
              dataIndex: 'url',
              key: 'url',
              width: 200,
              render: (_: unknown, record: TableDataItem, index: number) => (
                <Input
                  value={record.url}
                  onChange={(e) =>
                    handleFieldAndInstNameChange(e, {
                      index,
                      field: 'url',
                    })
                  }
                />
              ),
            },
          ],
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
                return {
                  ...item,
                  node_ids: [item.node_ids].flat(),
                  instance_type: pluginConfig.instance_type,
                  instance_id: item.url,
                };
              }),
            };
          },
        },
        edit: {
          formItems,
          getDefaultForm: (formData: TableDataItem) => {
            const url = formData?.child?.content?.config?.address || '';
            return {
              monitor_url: url,
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
            const instanceId = row.monitor_url;
            return {
              instance_id: instanceId,
              instance_name: instanceId,
            };
          },
          getConfigText: (formData: { [key: string]: string | number }) => {
            const configText = `[[inputs.$config_type]]
    address = "$monitor_url"
    interval = "$intervals"
    tags = { "instance_id"="$instance_id", "instance_type"="$instance_type", "collect_type"="$collect_type" }`;
            const instanceId = formData.monitor_url;
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
