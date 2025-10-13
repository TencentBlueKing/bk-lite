import React from 'react';
import { Form, Input, InputNumber } from 'antd';
import { useTranslation } from '@/utils/i18n';
import {
  InstNameConfig,
  IntegrationMonitoredObject,
} from '@/app/monitor/types/monitor';
import { TableDataItem } from '@/app/monitor/types';
import { cloneDeep } from 'lodash';

export const useNginxExporter = () => {
  const { t } = useTranslation();
  const pluginConfig = {
    collect_type: 'exporter',
    config_type: ['nginx'],
    collector: 'Nginx-Exporter',
    instance_type: 'nginx',
    object_name: 'Nginx',
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
        _dataSource[config.index][config.field] = _dataSource[config.index][
          config.dataIndex as string
        ] = e.target.value;
        extra.onTableDataChange?.(_dataSource);
      };

      const handleInputChange = (
        e: React.ChangeEvent<HTMLInputElement>,
        config: {
          index: number;
          field: string;
        }
      ) => {
        const _dataSource = cloneDeep(extra.dataSource || []);
        _dataSource[config.index][config.field] = e;
        extra.onTableDataChange?.(_dataSource);
      };

      const formItems = (
        <>
          <Form.Item label={t('monitor.integrations.listeningPort')} required>
            <Form.Item
              noStyle
              name="LISTEN_PORT"
              rules={[
                {
                  required: true,
                  message: t('common.required'),
                },
              ]}
            >
              <InputNumber
                className="w-[300px] mr-[10px]"
                min={1}
                precision={0}
              />
            </Form.Item>
            <span className="text-[12px] text-[var(--color-text-3)]">
              {t('monitor.integrations.listeningPortDes')}
            </span>
          </Form.Item>
          <Form.Item label={t('monitor.integrations.url')} required>
            <Form.Item
              noStyle
              name="NGINX_SCRAPE_URI"
              rules={[
                {
                  required: true,
                  message: t('common.required'),
                },
              ]}
            >
              <Input className="w-[300px] mr-[10px]" />
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
            ENV_LISTEN_PORT: null,
            ENV_NGINX_SCRAPE_URI: null,
          },
          defaultForm: {},
          columns: [
            {
              title: t('monitor.integrations.listeningPort'),
              dataIndex: 'ENV_LISTEN_PORT',
              key: 'ENV_LISTEN_PORT',
              width: 200,
              render: (_: unknown, record: TableDataItem, index: number) => (
                <InputNumber
                  value={record.ENV_LISTEN_PORT}
                  className="w-full"
                  min={1}
                  precision={0}
                  onChange={(e) =>
                    handleInputChange(e, {
                      index,
                      field: 'ENV_LISTEN_PORT',
                    })
                  }
                />
              ),
            },
            {
              title: t('monitor.integrations.url'),
              dataIndex: 'ENV_NGINX_SCRAPE_URI',
              key: 'ENV_NGINX_SCRAPE_URI',
              width: 200,
              render: (_: unknown, record: TableDataItem, index: number) => (
                <Input
                  value={record.ENV_HOST}
                  onChange={(e) =>
                    handleFieldAndInstNameChange(e, {
                      index,
                      field: 'ENV_NGINX_SCRAPE_URI',
                      dataIndex: 'instance_name',
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
                  ENV_LISTEN_PORT: String(item.ENV_LISTEN_PORT),
                  ENV_NGINX_SCRAPE_URI: String(item.ENV_NGINX_SCRAPE_URI),
                  node_ids: [item.node_ids].flat(),
                  instance_type: pluginConfig.instance_type,
                  instance_id: item.ENV_NGINX_SCRAPE_URI,
                };
              }),
            };
          },
        },
        edit: {
          formItems,
          getDefaultForm: (formData: TableDataItem) => {
            return formData?.base?.env_config || {};
          },
          getParams: (formData: TableDataItem, configForm: TableDataItem) => {
            ['LISTEN_PORT', 'NGINX_SCRAPE_URI'].forEach((item) => {
              if (formData[item]) {
                configForm.base.env_config[item] = String(formData[item]);
              }
            });
            return configForm;
          },
        },
        manual: {
          defaultForm: {},
          formItems,
          getParams: (row: TableDataItem) => {
            const instanceId = row.NGINX_SCRAPE_URI;
            return {
              instance_id: instanceId,
              instance_name: instanceId,
            };
          },
          getConfigText: () => {
            return '--';
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
