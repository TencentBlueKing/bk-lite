import React from 'react';
import { Form, Input, InputNumber } from 'antd';
import { useTranslation } from '@/utils/i18n';
import {
  InstNameConfig,
  IntergrationMonitoredObject,
} from '@/app/monitor/types/monitor';
import { TableDataItem } from '@/app/monitor/types';
import { useMongoDFormItems } from '../../common/mongoDBFormItems';
import { cloneDeep } from 'lodash';
import {
  extractMongoDBUrl,
  insertCredentialsToMongoDB,
  replaceTemplate,
} from '@/app/monitor/utils/intergration';

export const useMongoDBTelegraf = () => {
  const { t } = useTranslation();
  const mongoDBFormItems = useMongoDFormItems();
  const pluginConfig = {
    collect_type: 'database',
    config_type: ['mongodb'],
    collector: 'Telegraf',
    instance_type: 'mongodb',
    object_name: 'MongoDB',
  };

  return {
    getPluginCfg: (extra: {
      dataSource?: IntergrationMonitoredObject[];
      mode: 'manual' | 'auto' | 'edit';
      onTableDataChange?: (data: IntergrationMonitoredObject[]) => void;
    }) => {
      const isEdit = extra.mode === 'edit';
      const disabledForm = {
        password: isEdit,
        username: isEdit,
      };

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
          {mongoDBFormItems.getCommonFormItems(disabledForm)}
          <Form.Item required label={t('monitor.intergrations.host')}>
            <Form.Item
              noStyle
              name="host"
              rules={[
                {
                  required: true,
                  message: t('common.required'),
                },
              ]}
            >
              <Input className="w-[300px] mr-[10px]" disabled={isEdit} />
            </Form.Item>
            <span className="text-[12px] text-[var(--color-text-3)]">
              {t('monitor.intergrations.commonHostDes')}
            </span>
          </Form.Item>
          <Form.Item required label={t('monitor.intergrations.port')}>
            <Form.Item
              noStyle
              name="port"
              rules={[
                {
                  required: true,
                  message: t('common.required'),
                },
              ]}
            >
              <InputNumber
                className="mr-[10px] w-[303px]"
                min={1}
                precision={0}
                disabled={isEdit}
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
          formItems: mongoDBFormItems.getCommonFormItems(),
          initTableItems: {
            host: null,
            port: null,
          },
          defaultForm: {},
          columns: [
            {
              title: t('monitor.intergrations.host'),
              dataIndex: 'host',
              key: 'host',
              width: 200,
              render: (_: unknown, record: TableDataItem, index: number) => (
                <Input
                  value={record.host}
                  onChange={(e) =>
                    handleFieldAndInstNameChange(e, {
                      index,
                      field: 'host',
                      dataIndex: 'port',
                    })
                  }
                />
              ),
            },
            {
              title: t('monitor.intergrations.port'),
              dataIndex: 'port',
              key: 'port',
              width: 200,
              render: (_: unknown, record: TableDataItem, index: number) => (
                <InputNumber
                  value={record.port}
                  className="w-full"
                  min={1}
                  precision={0}
                  onChange={(val) =>
                    handlePortAndInstNameChange(val, {
                      index,
                      field: 'port',
                      dataIndex: 'host',
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
                  node_ids: [item.node_ids].flat(),
                  instance_type: pluginConfig.instance_type,
                  instance_id: `${item.host}:${item.port}`,
                };
              }),
            };
          },
        },
        edit: {
          formItems,
          getDefaultForm: (formData: TableDataItem) => {
            const server = formData?.child?.content?.config?.servers?.[0] || '';
            return extractMongoDBUrl(server);
          },
          getParams: (
            row: IntergrationMonitoredObject,
            config: TableDataItem
          ) => {
            return config;
          },
        },
        manual: {
          defaultForm: {},
          formItems,
          getParams: (row: TableDataItem) => {
            const instanceId = `${row.host}:${row.port}`;
            return {
              instance_id: instanceId,
              instance_name: instanceId,
            };
          },
          getConfigText: (formData: { [key: string]: string | number }) => {
            const configText = `[[inputs.$config_type]]
    servers = ["mongodb://$host:$port/?connect=direct"]
    interval = "$intervals"
    tags = { "instance_id"="$instance_id", "instance_type"="$instance_type", "collect_type"="$collect_type" }`;
            const instanceId = `${formData.host}:${formData.port}`;
            const params: any = {
              ...formData,
              instance_id: instanceId,
              instance_type: pluginConfig.instance_type,
              collect_type: pluginConfig.collect_type,
              config_type: pluginConfig.config_type[0] || '',
            };
            const text = insertCredentialsToMongoDB(configText, params);
            return replaceTemplate(text, params);
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
