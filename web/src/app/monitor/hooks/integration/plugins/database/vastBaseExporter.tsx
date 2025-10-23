import React from 'react';
import { Form, Input, InputNumber } from 'antd';
import { useTranslation } from '@/utils/i18n';
import {
  InstNameConfig,
  IntegrationMonitoredObject,
} from '@/app/monitor/types/integration';
import { TableDataItem } from '@/app/monitor/types';
import { useVastBaseExporterFormItems } from '../../common/vastBaseExporterFormItems';
import { cloneDeep } from 'lodash';

export const useVastBaseExporter = () => {
  const { t } = useTranslation();
  const vastBaseExporterFormItems = useVastBaseExporterFormItems();
  const pluginConfig = {
    collect_type: 'exporter',
    config_type: ['vastbase'],
    collector: 'VastBase-Exporter',
    instance_type: 'vastbase',
    object_name: 'VastBase',
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
          {vastBaseExporterFormItems.getCommonFormItems()}
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
              name="SQL_EXPORTER_HOST"
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
              name="SQL_EXPORTER_PORT"
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
          formItems: vastBaseExporterFormItems.getCommonFormItems('auto'),
          initTableItems: {
            ENV_LISTEN_PORT: null,
            ENV_SQL_EXPORTER_HOST: null,
            ENV_SQL_EXPORTER_PORT: null,
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
              dataIndex: 'ENV_SQL_EXPORTER_HOST',
              key: 'ENV_SQL_EXPORTER_HOST',
              width: 200,
              render: (_: unknown, record: TableDataItem, index: number) => (
                <Input
                  value={record.ENV_SQL_EXPORTER_HOST}
                  onChange={(e) =>
                    handleFieldAndInstNameChange(e, {
                      index,
                      field: 'ENV_SQL_EXPORTER_HOST',
                      dataIndex: 'ENV_SQL_EXPORTER_PORT',
                    })
                  }
                />
              ),
            },
            {
              title: t('monitor.integrations.port'),
              dataIndex: 'ENV_SQL_EXPORTER_PORT',
              key: 'ENV_SQL_EXPORTER_PORT',
              width: 200,
              render: (_: unknown, record: TableDataItem, index: number) => (
                <InputNumber
                  value={record.ENV_SQL_EXPORTER_PORT}
                  className="w-full"
                  min={1}
                  precision={0}
                  onChange={(val) =>
                    handlePortAndInstNameChange(val, {
                      index,
                      field: 'ENV_SQL_EXPORTER_PORT',
                      dataIndex: 'ENV_SQL_EXPORTER_HOST',
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
            const configs: any = [
              {
                type: pluginConfig.config_type[0],
                ...row,
              },
            ];
            if (row.ENV_SCRAPE_TIMEOUT) {
              configs[0].ENV_SCRAPE_TIMEOUT = row.ENV_SCRAPE_TIMEOUT + 's';
            }
            if (row.ENV_MAX_CONNECTION_LIFETIME) {
              configs[0].ENV_MAX_CONNECTION_LIFETIME =
                row.ENV_MAX_CONNECTION_LIFETIME + 'm';
            }
            return {
              configs,
              collect_type: pluginConfig.collect_type,
              collector: pluginConfig.collector,
              instances: dataSource.map((item: TableDataItem) => {
                delete item.key;
                const target: TableDataItem | undefined = config.nodeList.find(
                  (tex: IntegrationMonitoredObject) => item.node_ids === tex.id
                );
                return {
                  ...item,
                  ENV_LISTEN_PORT: String(item.ENV_LISTEN_PORT),
                  ENV_SQL_EXPORTER_PORT: String(item.ENV_SQL_EXPORTER_PORT),
                  node_ids: [item.node_ids].flat(),
                  instance_type: pluginConfig.instance_type,
                  instance_id: `${target?.cloud_region}_${item.ENV_SQL_EXPORTER_HOST}_${item.ENV_SQL_EXPORTER_PORT}`,
                };
              }),
            };
          },
        },
        edit: {
          formItems,
          getDefaultForm: (formData: TableDataItem) => {
            const defaultForm = formData?.base?.env_config || {};
            if (defaultForm.MAX_CONNECTION_LIFETIME) {
              defaultForm.MAX_CONNECTION_LIFETIME =
                defaultForm.MAX_CONNECTION_LIFETIME.replace('m', '');
            }
            if (defaultForm.SCRAPE_TIMEOUT) {
              defaultForm.SCRAPE_TIMEOUT = defaultForm.SCRAPE_TIMEOUT.replace(
                's',
                ''
              );
            }
            return defaultForm;
          },
          getParams: (formData: TableDataItem, configForm: TableDataItem) => {
            [
              'LISTEN_PORT',
              'SQL_EXPORTER_USER',
              'SQL_EXPORTER_PASS',
              'SQL_EXPORTER_DB_NAME',
              'COLLECTOR_REFS',
              'SCRAPE_TIMEOUT',
              'SQL_EXPORTER_PORT',
              'MAX_CONNECTION_LIFETIME',
              'SQL_EXPORTER_HOST',
              'SQL_EXPORTER_DB_TYPE',
            ].forEach((item) => {
              if (formData[item]) {
                if (
                  ['MAX_CONNECTION_LIFETIME', 'SCRAPE_TIMEOUT'].includes(item)
                ) {
                  configForm.base.env_config[item] =
                    formData[item] + `${item === 'SCRAPE_TIMEOUT' ? 's' : 'm'}`;
                  return;
                }
                configForm.base.env_config[item] = String(formData[item]);
              } else {
                delete configForm.base.env_config[item];
              }
            });
            return configForm;
          },
        },
        manual: {
          defaultForm: {},
          formItems,
          getParams: (row: TableDataItem) => {
            const instanceId = `${row.SQL_EXPORTER_HOST}:${row.SQL_EXPORTER_PORT}`;
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
