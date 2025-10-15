import React from 'react';
import { Form, Input, InputNumber } from 'antd';
import { useTranslation } from '@/utils/i18n';
import {
  InstNameConfig,
  IntegrationMonitoredObject,
} from '@/app/monitor/types/integration';
import { TableDataItem } from '@/app/monitor/types';
import { usePostgresExporterFormItems } from '../../common/postgresExporterFormItems';
import { cloneDeep } from 'lodash';

export const usePostgresExporter = () => {
  const { t } = useTranslation();
  const postgresFormItems = usePostgresExporterFormItems();
  const pluginConfig = {
    collect_type: 'exporter',
    config_type: ['postgres'],
    collector: 'Postgres-Exporter',
    instance_type: 'postgres',
    object_name: 'Postgres',
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
        const fieldValue =
          _dataSource[config.index][config.dataIndex as string];
        _dataSource[config.index][config.field] = e.target.value;
        _dataSource[config.index].instance_name =
          e.target.value + `:${fieldValue || ''}`;
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

      const handlePortAndInstNameChange = (
        val: number,
        config: {
          index: number;
          field: string;
          dataIndex: string;
        }
      ) => {
        const _dataSource = cloneDeep(extra.dataSource || []);
        const host = _dataSource[config.index][config.dataIndex] || '';
        _dataSource[config.index][config.field] = val;
        _dataSource[config.index].instance_name = `${host}:${val || ''}`;
        extra.onTableDataChange?.(_dataSource);
      };

      const formItems = (
        <>
          {postgresFormItems.getCommonFormItems()}
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
          <Form.Item label={t('monitor.integrations.host')} required>
            <Form.Item
              noStyle
              name="DATA_SOURCE_HOST"
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
              {t('monitor.integrations.commonHostDes')}
            </span>
          </Form.Item>
          <Form.Item label={t('monitor.integrations.port')} required>
            <Form.Item
              noStyle
              name="DATA_SOURCE_PORT"
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
              {t('monitor.integrations.commonPortDes')}
            </span>
          </Form.Item>
        </>
      );

      const config = {
        auto: {
          formItems: postgresFormItems.getCommonFormItems('auto'),
          initTableItems: {
            ENV_LISTEN_PORT: null,
            ENV_DATA_SOURCE_HOST: null,
            ENV_DATA_SOURCE_PORT: null,
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
              title: t('monitor.integrations.host'),
              dataIndex: 'ENV_DATA_SOURCE_HOST',
              key: 'ENV_DATA_SOURCE_HOST',
              width: 200,
              render: (_: unknown, record: TableDataItem, index: number) => (
                <Input
                  value={record.ENV_DATA_SOURCE_HOST}
                  onChange={(e) =>
                    handleFieldAndInstNameChange(e, {
                      index,
                      field: 'ENV_DATA_SOURCE_HOST',
                      dataIndex: 'ENV_DATA_SOURCE_PORT',
                    })
                  }
                />
              ),
            },
            {
              title: t('monitor.integrations.port'),
              dataIndex: 'ENV_DATA_SOURCE_PORT',
              key: 'ENV_DATA_SOURCE_PORT',
              width: 200,
              render: (_: unknown, record: TableDataItem, index: number) => (
                <InputNumber
                  value={record.ENV_DATA_SOURCE_PORT}
                  className="w-full"
                  min={1}
                  precision={0}
                  onChange={(val) =>
                    handlePortAndInstNameChange(val, {
                      index,
                      field: 'ENV_DATA_SOURCE_PORT',
                      dataIndex: 'ENV_DATA_SOURCE_HOST',
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
                  ENV_DATA_SOURCE_PORT: String(item.ENV_DATA_SOURCE_PORT),
                  node_ids: [item.node_ids].flat(),
                  instance_type: pluginConfig.instance_type,
                  instance_id: `${item.ENV_DATA_SOURCE_HOST}:${item.ENV_DATA_SOURCE_PORT}`,
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
              'LISTEN_PORT',
              'DATA_SOURCE_HOST',
              'DATA_SOURCE_PORT',
              'DATA_SOURCE_PASS',
              'DATA_SOURCE_DB',
              'DATA_SOURCE_USER',
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
            const instanceId = `${row.DATA_SOURCE_HOST}:${row.DATA_SOURCE_PORT}`;
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
