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

export const useWebLogicJmx = () => {
  const { t } = useTranslation();
  const webLogicFormItems = useJmxCommonFormItems();
  const pluginConfig = {
    collect_type: 'jmx',
    config_type: ['weblogic'],
    collector: 'WebLogic-JMX',
    instance_type: 'weblogic',
    object_name: 'WebLogic',
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
          {webLogicFormItems.getCommonFormItems(disabledForm)}
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
          formItems: webLogicFormItems.getCommonFormItems(),
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
                const target: TableDataItem | undefined = config.nodeList.find(
                  (tex: IntegrationMonitoredObject) => item.node_ids === tex.id
                );
                return {
                  ...item,
                  ENV_LISTEN_PORT: String(item.ENV_LISTEN_PORT),
                  node_ids: [item.node_ids].flat(),
                  instance_type: pluginConfig.instance_type,
                  instance_id: `${target?.cloud_region}_${item.jmx_url}`,
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
startDelaySeconds: 0
lowercaseOutputName: true
lowercaseOutputLabelNames: true
whitelistObjectNames:
  - "com.bea:Name=*,Type=ServerRuntime"
  - "com.bea:ServerRuntime=*,Type=ApplicationRuntime,*"
  - "com.bea:ServerRuntime=*,Type=JDBCDataSourceRuntime,*"
  - "com.bea:ServerRuntime=*,Type=JMSDestinationRuntime,*"
  - "com.bea:ServerRuntime=*,Type=JDBCStoreRuntime,*"
  - "com.bea:ServerRuntime=*,Type=FileStoreRuntime,*"
  - "com.bea:ServerRuntime=*,Type=SAFRemoteEndpointRuntime,*"
  - "com.bea:ServerRuntime=*,Type=ThreadPoolRuntime,*"
  - "com.bea:ServerRuntime=*,Type=JMSRuntime,*"
  - "com.bea:ServerRuntime=*,Type=SAFRuntime,*"
  - "com.bea:ServerRuntime=*,Type=WorkManagerRuntime,*"
  - "com.bea:ServerRuntime=*,Type=MessagingBridgeRuntime,*"
  - "com.bea:ServerRuntime=*,Type=PersistentStoreRuntime,*"
  - "com.bea:ServerRuntime=*,Type=WebServerRuntime,*"


rules:
  # ex: com.bea<ServerRuntime=AdminServer, Name=default, ApplicationRuntime=moduleJMS, Type=WorkManagerRuntime><>CompletedRequests
  - pattern: "^com.bea<ServerRuntime=(.+), Name=(.+), (.+)Runtime=(.*), Type=(.+)Runtime><>(.+):"
    name: weblogic_$3_$5_$6
    attrNameSnakeCase: true
    labels:
      runtime: $1
      name: $2
      application: $4

  # ex: com.bea<ServerRuntime=AdminServer, Name=dsName, Type=JDBCDataSourceRuntime><>Metric
  - pattern: "^com.bea<ServerRuntime=(.+), Name=(.+), Type=(.+)Runtime><>(.+):"
    name: weblogic_$3_$4
    attrNameSnakeCase: true
    labels:
      runtime: $1
      name: $2

  # ex: com.bea<ServerRuntime=AdminServer, Name=bea_wls_cluster_internal, Type=ApplicationRuntime><OverallHealthStateJMX>IsCritical
  - pattern: "^com.bea<ServerRuntime=(.+), Name=(.+), Type=(.+)Runtime><(.+)>(.+):"
    name: weblogic_$3_$4_$5
    attrNameSnakeCase: true
    labels:
      runtime: $1
      name: $2`;
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
