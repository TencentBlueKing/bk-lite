import React from 'react';
import { Form, Input, InputNumber } from 'antd';
import { useTranslation } from '@/utils/i18n';
import {
  InstNameConfig,
  IntegrationMonitoredObject,
} from '@/app/monitor/types/integration';
import { TableDataItem } from '@/app/monitor/types';
import { useRabbitMQExporterFormItems } from '../../common/rabbitMQExporterFormItems';
import { cloneDeep } from 'lodash';

export const useRabbitMQExporter = () => {
  const { t } = useTranslation();
  const rabbitMQExporterFormItems = useRabbitMQExporterFormItems();
  const pluginConfig = {
    collect_type: 'exporter',
    config_type: ['rabbitmq'],
    collector: 'RabbitMQ-Exporter',
    instance_type: 'rabbitmq',
    object_name: 'RabbitMQ',
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
        _dataSource[config.index][config.field] =
          config.field === 'ENV_PUBLISH_ADDR' ? e.target.value : e;
        extra.onTableDataChange?.(_dataSource);
      };

      const formItems = (
        <>
          {rabbitMQExporterFormItems.getCommonFormItems()}
          <Form.Item label={t('monitor.integrations.addressDes')} required>
            <Form.Item
              noStyle
              name="RABBIT_URL"
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
          <Form.Item label={t('monitor.integrations.publishPort')} required>
            <Form.Item
              noStyle
              name="PUBLISH_PORT"
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
              {t('monitor.integrations.publishPortDes')}
            </span>
          </Form.Item>
          <Form.Item label={t('monitor.integrations.publishAddress')} required>
            <Form.Item
              noStyle
              name="PUBLISH_ADDR"
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
              {t('monitor.integrations.publishAddressDes')}
            </span>
          </Form.Item>
        </>
      );

      const config = {
        auto: {
          formItems: rabbitMQExporterFormItems.getCommonFormItems('auto'),
          initTableItems: {
            ENV_PUBLISH_PORT: null,
            ENV_RABBIT_URL: null,
            ENV_PUBLISH_ADDR: null,
          },
          defaultForm: {
            ENV_RABBIT_TIMEOUT: 60,
          },
          columns: [
            {
              title: t('monitor.integrations.publishAddress'),
              dataIndex: 'ENV_PUBLISH_ADDR',
              key: 'ENV_PUBLISH_ADDR',
              width: 200,
              render: (_: unknown, record: TableDataItem, index: number) => (
                <Input
                  value={record.ENV_HOST}
                  onChange={(e) =>
                    handleInputChange(e, {
                      index,
                      field: 'ENV_PUBLISH_ADDR',
                    })
                  }
                />
              ),
            },
            {
              title: t('monitor.integrations.publishPort'),
              dataIndex: 'ENV_PUBLISH_PORT',
              key: 'ENV_PUBLISH_PORT',
              width: 200,
              render: (_: unknown, record: TableDataItem, index: number) => (
                <InputNumber
                  value={record.ENV_PUBLISH_PORT}
                  className="w-full"
                  min={1}
                  precision={0}
                  onChange={(e) =>
                    handleInputChange(e, {
                      index,
                      field: 'ENV_PUBLISH_PORT',
                    })
                  }
                />
              ),
            },
            {
              title: t('monitor.integrations.url'),
              dataIndex: 'ENV_RABBIT_URL',
              key: 'ENV_RABBIT_URL',
              width: 200,
              render: (_: unknown, record: TableDataItem, index: number) => (
                <Input
                  value={record.ENV_HOST}
                  onChange={(e) =>
                    handleFieldAndInstNameChange(e, {
                      index,
                      field: 'ENV_RABBIT_URL',
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
                  ENV_RABBIT_TIMEOUT: String(row.ENV_RABBIT_TIMEOUT),
                },
              ],
              collect_type: pluginConfig.collect_type,
              collector: pluginConfig.collector,
              instances: dataSource.map((item: TableDataItem) => {
                delete item.key;
                return {
                  ...item,
                  ENV_PUBLISH_PORT: String(item.ENV_PUBLISH_PORT),
                  ENV_RABBIT_URL: String(item.ENV_RABBIT_URL),
                  ENV_PUBLISH_ADDR: String(item.ENV_PUBLISH_ADDR),
                  node_ids: [item.node_ids].flat(),
                  instance_type: pluginConfig.instance_type,
                  instance_id: item.ENV_RABBIT_URL,
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
            [
              'PUBLISH_PORT',
              'RABBIT_URL',
              'PUBLISH_ADDR',
              'RABBIT_USER',
              'RABBIT_PASSWORD',
              'RABBIT_TIMEOUT',
              'RABBIT_CONNECTION',
            ].forEach((item) => {
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
            const instanceId = row.RABBIT_URL;
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
