import React from 'react';
import { Form, Input, InputNumber } from 'antd';
import { useTranslation } from '@/utils/i18n';
import {
  InstNameConfig,
  IntegrationMonitoredObject,
} from '@/app/monitor/types/integration';
import { TableDataItem } from '@/app/monitor/types';
import { useJmxCommonFormItems } from '../../common/jmxCommonFormItems';
import { cloneDeep } from 'lodash';
import { replaceTemplate } from '@/app/monitor/utils/integration';

export const useJbossJmx = () => {
  const { t } = useTranslation();
  const activeMQFormItems = useJmxCommonFormItems();
  const pluginConfig = {
    collect_type: 'jmx',
    config_type: ['jboss'],
    collector: 'JBoss-JMX',
    instance_type: 'jboss',
    object_name: 'JBoss',
  };

  return {
    getPluginCfg: (extra: {
      dataSource?: IntegrationMonitoredObject[];
      mode: 'manual' | 'auto' | 'edit';
      onTableDataChange?: (data: IntegrationMonitoredObject[]) => void;
    }) => {
      const isEdit = extra.mode === 'edit';
      const disabledForm = {
        monitor_url: true,
        username: true,
        password: true,
      };

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
          {activeMQFormItems.getCommonFormItems(disabledForm)}
          <Form.Item required label="JmxUrl">
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
              <Input className="w-[300px] mr-[10px]" disabled={isEdit} />
            </Form.Item>
            <span className="text-[12px] text-[var(--color-text-3)]">
              {t('monitor.integrations.urlDes')}
            </span>
          </Form.Item>
          <Form.Item label={t('monitor.integrations.listeningPort')}>
            <Form.Item noStyle name="LISTEN_PORT">
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
        </>
      );

      const config = {
        auto: {
          formItems: activeMQFormItems.getCommonFormItems(),
          initTableItems: {
            jmx_url: null,
            ENV_LISTEN_PORT: null,
          },
          defaultForm: {},
          columns: [
            {
              title: t('monitor.integrations.url'),
              dataIndex: 'jmx_url',
              key: 'jmx_url',
              width: 200,
              render: (_: unknown, record: TableDataItem, index: number) => (
                <Input
                  value={record.jmx_url}
                  onChange={(e) =>
                    handleFieldAndInstNameChange(e, {
                      index,
                      field: 'jmx_url',
                    })
                  }
                />
              ),
            },
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
                  node_ids: [item.node_ids].flat(),
                  instance_type: pluginConfig.instance_type,
                  instance_id: item.jmx_url,
                };
              }),
            };
          },
        },
        edit: {
          formItems,
          getDefaultForm: (formData: TableDataItem) => {
            const base: Record<string, any> = cloneDeep(
              formData?.base?.content || {}
            );
            const envConfig: Record<string, any> = cloneDeep(
              formData?.base?.env_config || {}
            );
            return {
              monitor_url: base.jmxUrl || '',
              username: base.username,
              password: base.password,
              LISTEN_PORT: envConfig.LISTEN_PORT || null,
            };
          },
          getParams: (
            row: IntegrationMonitoredObject,
            config: TableDataItem
          ) => {
            config.base.env_config.LISTEN_PORT = String(row.LISTEN_PORT);
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
            const configText = `username: $username
password: $password
jmxUrl: $monitor_url
ssl: false
lowercaseOutputName: true
lowercaseOutputLabelNames: true
whitelistObjectNames:
 - "jboss.as:subsystem=messaging-activemq,server=*,jms-queue=*"
 - "jboss.as:subsystem=messaging-activemq,server=*,jms-topic=*"
 - "jboss.as:subsystem=datasources,data-source=*,statistics=*"
 - "jboss.as:subsystem=datasources,xa-data-source=*,statistics=*"
 - "jboss.as:subsystem=transactions*"
 - "jboss.as:subsystem=undertow,server=*,http-listener=*"
 - "jboss.as:subsystem=undertow,server=*,https-listener=*"
 # - "java.lang:*"
rules:
  - pattern: "^jboss.as<subsystem=messaging-activemq, server=.+, jms-(queue|topic)=(.+)><>(.+):"
    attrNameSnakeCase: true
    name: wildfly_messaging_$3
    labels:
      $1: $2

  - pattern: "^jboss.as<subsystem=datasources, (?:xa-)*data-source=(.+), statistics=(.+)><>(.+):"
    attrNameSnakeCase: true
    name: wildfly_datasource_$2_$3
    labels:
      source_name: $1

  - pattern: "^jboss.as<subsystem=transactions><>number_of_(.+):"
    attrNameSnakeCase: true
    name: wildfly_transaction_$1

  - pattern: "^jboss.as<subsystem=undertow, server=(.+), (http[s]?-listener)=(.+)><>(bytes_.+|error_count|processing_time|request_count):"
    attrNameSnakeCase: true
    name: wildfly_undertow_$4
    labels:
      server_name: $1
      listener: $3`;
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
