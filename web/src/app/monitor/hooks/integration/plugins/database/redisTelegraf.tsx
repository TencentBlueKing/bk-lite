import React from 'react';
import { Form, Input, InputNumber } from 'antd';
import { useTranslation } from '@/utils/i18n';
import {
  InstNameConfig,
  IntegrationMonitoredObject,
} from '@/app/monitor/types/integration';
import { TableDataItem } from '@/app/monitor/types';
import { useRedisFormItems } from '../../common/redisFormItems';
import { cloneDeep } from 'lodash';
import {
  extractMongoDBUrl,
  replaceTemplate,
} from '@/app/monitor/utils/integration';

export const useRedisTelegraf = () => {
  const { t } = useTranslation();
  const redisFormItems = useRedisFormItems();
  const pluginConfig = {
    collect_type: 'database',
    config_type: ['redis'],
    collector: 'Telegraf',
    instance_type: 'redis',
    object_name: 'Redis',
  };

  return {
    getPluginCfg: (extra: {
      dataSource?: IntegrationMonitoredObject[];
      mode: 'manual' | 'auto' | 'edit';
      onTableDataChange?: (data: IntegrationMonitoredObject[]) => void;
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
          {redisFormItems.getCommonFormItems(disabledForm)}
          <Form.Item required label={t('monitor.integrations.host')}>
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
              {t('monitor.integrations.commonHostDes')}
            </span>
          </Form.Item>
          <Form.Item required label={t('monitor.integrations.port')}>
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
              {t('monitor.integrations.commonPortDes')}
            </span>
          </Form.Item>
        </>
      );

      const config = {
        auto: {
          formItems: redisFormItems.getCommonFormItems(),
          initTableItems: {
            host: null,
            port: null,
          },
          defaultForm: {},
          columns: [
            {
              title: t('monitor.integrations.host'),
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
              title: t('monitor.integrations.port'),
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
                  instance_id: `${target?.cloud_region}_${item.host}_${item.port}`,
                };
              }),
            };
          },
        },
        edit: {
          formItems,
          getDefaultForm: (formData: TableDataItem) => {
            const server = formData?.child?.content?.config?.servers?.[0] || '';
            const configId = (formData?.child?.id || '').toUpperCase();
            const password =
              formData?.child?.env_config?.[`PASSWORD__${configId}`];
            return {
              ...extractMongoDBUrl(server),
              ENV_PASSWORD: password,
            };
          },
          getParams: (
            row: IntegrationMonitoredObject,
            config: TableDataItem
          ) => {
            const configId = (config.child.id || '').toUpperCase();
            config.child.env_config[`PASSWORD__${configId}`] = row.ENV_PASSWORD;
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
    servers = ["tcp://$host:$port"]
    username = "$username"
    password = "$password" 
    interval = "$intervals"
    tags = { "instance_id"="$instance_id", "instance_type"="$instance_type", "collect_type"="$collect_type" }`;
            const instanceId = `${formData.host}:${formData.port}`;
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
