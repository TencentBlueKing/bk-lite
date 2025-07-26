import React from 'react';
import { Form, Input, InputNumber } from 'antd';
import { useTranslation } from '@/utils/i18n';
import {
  InstNameConfig,
  IntergrationMonitoredObject,
} from '@/app/monitor/types/monitor';
import { TableDataItem } from '@/app/monitor/types';
import { useGreenPlumExporterFormItems } from '../../common/greenPlumExporterFormItems';
import { cloneDeep } from 'lodash';

export const useGreenPlumExporter = () => {
  const { t } = useTranslation();
  const greenPlumExporterFormItems = useGreenPlumExporterFormItems();
  const pluginConfig = {
    collect_type: 'exporter',
    config_type: ['greenplum'],
    collector: 'GreenPlum-Exporter',
    instance_type: 'greenplum',
    object_name: 'GreenPlum',
  };

  return {
    getPluginCfg: (extra: {
      dataSource?: IntergrationMonitoredObject[];
      mode: 'manual' | 'auto' | 'edit';
      onTableDataChange?: (data: IntergrationMonitoredObject[]) => void;
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
          {greenPlumExporterFormItems.getCommonFormItems()}
          <Form.Item label={t('monitor.intergrations.listeningPort')} required>
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
              {t('monitor.intergrations.listeningPortDes')}
            </span>
          </Form.Item>
          <Form.Item label={t('monitor.intergrations.host')} required>
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
              {t('monitor.intergrations.commonHostDes')}
            </span>
          </Form.Item>
          <Form.Item label={t('monitor.intergrations.port')} required>
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
              {t('monitor.intergrations.commonPortDes')}
            </span>
          </Form.Item>
        </>
      );

      const config = {
        auto: {
          formItems: greenPlumExporterFormItems.getCommonFormItems('auto'),
          initTableItems: {
            ENV_LISTEN_PORT: null,
            ENV_SQL_EXPORTER_PORT: null,
            ENV_SQL_EXPORTER_HOST: null,
          },
          defaultForm: {},
          columns: [
            {
              title: t('monitor.intergrations.listeningPort'),
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
              title: t('monitor.intergrations.host'),
              dataIndex: 'ENV_SQL_EXPORTER_HOST',
              key: 'ENV_SQL_EXPORTER_HOST',
              width: 200,
              render: (_: unknown, record: TableDataItem, index: number) => (
                <Input
                  value={record.ENV_HOST}
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
              title: t('monitor.intergrations.port'),
              dataIndex: 'ENV_SQL_EXPORTER_PORT',
              key: 'ENV_SQL_EXPORTER_PORT',
              width: 200,
              render: (_: unknown, record: TableDataItem, index: number) => (
                <InputNumber
                  value={record.ENV_PORT}
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
            row: IntergrationMonitoredObject,
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
                  ENV_SQL_EXPORTER_PORT: String(item.ENV_SQL_EXPORTER_PORT),
                  node_ids: [item.node_ids].flat(),
                  instance_type: pluginConfig.instance_type,
                  instance_id: `${item.ENV_SQL_EXPORTER_HOST}:${item.ENV_SQL_EXPORTER_PORT}`,
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
              'SQL_EXPORTER_PORT',
              'SQL_EXPORTER_HOST',
              'SQL_EXPORTER_USER',
              'SQL_EXPORTER_PASS',
              'SQL_EXPORTER_DB_NAME',
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
            const instanceId = `${row.SQL_EXPORTER_PORT}:${row.SQL_EXPORTER_PORT}`;
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
