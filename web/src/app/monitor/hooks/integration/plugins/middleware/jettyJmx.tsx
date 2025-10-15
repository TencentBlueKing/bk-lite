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

export const useJettyJmx = () => {
  const { t } = useTranslation();
  const activeMQFormItems = useJmxCommonFormItems();
  const pluginConfig = {
    collect_type: 'jmx',
    config_type: ['jetty'],
    collector: 'Jetty-JMX',
    instance_type: 'jetty',
    object_name: 'Jetty',
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
startDelaySeconds: 0
lowercaseOutputName: true
lowercaseOutputLabelNames: true
rules:
  - pattern: java.lang<type=Memory><HeapMemoryUsage>max
    name: jvm_memory_heap_usage_max
  - pattern: java.lang<type=Memory><HeapMemoryUsage>used
    name: jvm_memory_heap_usage_used
  - pattern: java.lang<type=Memory><HeapMemoryUsage>committed
    name: jvm_memory_heap_usage_committed
  - pattern: java.lang<type=Memory><HeapMemoryUsage>init
    name: jvm_memory_heap_usage_init
  - pattern: java.lang<type=Memory><NonHeapMemoryUsage>max
    name: jvm_memory_nonheap_usage_max
  - pattern: java.lang<type=Memory><NonHeapMemoryUsage>used
    name: jvm_memory_nonheap_usage_used
  - pattern: java.lang<type=Memory><NonHeapMemoryUsage>committed
    name: jvm_memory_nonheap_usage_committed
  - pattern: java.lang<type=Memory><NonHeapMemoryUsage>init
    name: jvm_memory_nonheap_usage_init
  - pattern: org.eclipse.jetty.io<type=arraybytebufferpool, id=0><>heapMemory
    name: jetty_bufferpool_heapMemory
  - pattern: org.eclipse.jetty.deploy<type=deploymentmanager, id=(.+)><>stopTimeout
    name: jetty_deploymentmanager_stopTimeout
    labels:
      id: "$1"
  - pattern: org.eclipse.jetty.deploy.providers<type=webappprovider, id=(.+)><>stopTimeout
    name: jetty_webappprovider_stopTimeout
    labels:
      id: "$1"
  - pattern: org.eclipse.jetty.io<type=arraybytebufferpool, id=(.+)><>heapMemory
    name: jetty_arraybufferpool_heapMemory
    labels:
      id: "$1"
  - pattern: org.eclipse.jetty.io<type=arraybytebufferpool, id=(.+)><>directByteBufferCount
    name: jetty_arraybufferpool_directByteBufferCount
    labels:
      id: "$1"
  - pattern: org.eclipse.jetty.io<type=arraybytebufferpool, id=(.+)><>directMemory
    name: jetty_arraybufferpool_directMemory
    labels:
      id: "$1"
  - pattern: org.eclipse.jetty.io<type=arraybytebufferpool, id=(.+)><>heapByteBufferCount
    name: jetty_arraybufferpool_heapByteBufferCount
    labels:
      id: "$1"
  - pattern: org.eclipse.jetty.io<context=(.+), type=managedselector, id=(.+)><>stopTimeout
    name: jetty_managedselector_stopTimeout
    labels:
      context: "$1"
      id:  "$2"
  - pattern: org.eclipse.jetty.io<context=(.+), type=managedselector, id=(.+)><>averageSelectedKeys
    name: jetty_managedselector_averageSelectedKeys
    labels:
      context: "$1"
      id: "$2"
  - pattern: org.eclipse.jetty.io<context=(.+), type=managedselector, id=(.+)><>maxSelectedKeys
    name: jetty_managedselector_maxSelectedKeys
    labels:
      context: "$1"
      id: "$2"
  - pattern: org.eclipse.jetty.io<context=(.+), type=managedselector, id=(.+)><>selectCount
    name: jetty_managedselector_selectCount
    labels:
      context: "$1"
      id: "$2"
  - pattern: org.eclipse.jetty.io<context=(.+), type=managedselector, id=(.+)><>totalKeys
    name: jetty_managedselector_totalKeys
    labels:
      context: "$1"
      id: "$2"
  - pattern: org.eclipse.jetty.server<context=(.+), type=httpconfiguration, id=(.+)><>responseHeaderSize
    name: jetty_httpconfiguration_responseHeaderSize
    labels:
      context: "$1"
      id: "$2"
  - pattern: org.eclipse.jetty.server<context=(.+), type=httpconfiguration, id=(.+)><>requestHeaderSize
    name: jetty_httpconfiguration_requestHeaderSize
    labels:
      context: "$1"
      id: "$2"
  - pattern: org.eclipse.jetty.server<context=(.+), type=httpconfiguration, id=(.+)><>maxErrorDispatches
    name: jetty_httpconfiguration_maxErrorDispatches
    labels:
      context: "$1"
      id: "$2"
  - pattern: org.eclipse.jetty.server<context=(.+), type=httpconfiguration, id=(.+)><>idleTimeout
    name: jetty_httpconfiguration_idleTimeout
    labels:
      context: "$1"
      id: "$2"
  - pattern: org.eclipse.jetty.server<context=(.+), type=httpconfiguration, id=(.+)><>outputBufferSize
    name: jetty_httpconfiguration_outputBufferSize
    labels:
      context: "$1"
      id: "$2"
  - pattern: org.eclipse.jetty.server<context=(.+), type=httpconfiguration, id=(.+)><>headerCacheSize
    name: jetty_httpconfiguration_headerCacheSize
    labels:
      context: "$1"
      id: "$2"
  - pattern: org.eclipse.jetty.server<context=(.+), type=httpconfiguration, id=(.+)><>minRequestDataRate
    name: jetty_httpconfiguration_minRequestDataRate
    labels:
      context: "$1"
      id: "$2"
  - pattern: org.eclipse.jetty.server<context=(.+), type=httpconfiguration, id=(.+)><>outputAggregationSize
    name: jetty_httpconfiguration_outputAggregationSize
    labels:
      context: "$1"
      id: "$2"
  - pattern: org.eclipse.jetty.server<context=(.+), type=httpconfiguration, id=(.+)><>blockingTimeout
    name: jetty_httpconfiguration_blockingTimeout
    labels:
      context: "$1"
      id: "$2"
  - pattern: org.eclipse.jetty.server<context=(.+), type=httpconfiguration, id=(.+)><>minResponseDataRate
    name: jetty_httpconfiguration_minResponseDataRate
    labels:
      context: "$1"
      id: "$2"
  - pattern: org.eclipse.jetty.server<context=(.+), type=serverconnector, id=(.+)><>stopTimeout
    name: jetty_serverconnector_stopTimeout
    labels:
      context: "$1"
      id: "$2"
  - pattern: org.eclipse.jetty.server<context=(.+), type=serverconnector, id=(.+)><>acceptQueueSize
    name: jetty_serverconnector_acceptQueueSize
    labels:
      context: "$1"
      id: "$2"
  - pattern: org.eclipse.jetty.server<context=(.+), type=serverconnector, id=(.+)><>acceptedReceiveBufferSize
    name: jetty_serverconnector_acceptedReceiveBufferSize
    labels:
      context: "$1"
      id: "$2"
  - pattern: org.eclipse.jetty.server<context=(.+), type=serverconnector, id=(.+)><>acceptedSendBufferSize
    name: jetty_serverconnector_acceptedSendBufferSize
    labels:
      context: "$1"
      id: "$2"
  - pattern: org.eclipse.jetty.server<context=(.+), type=serverconnector, id=(.+)><>idleTimeout
    name: jetty_serverconnector_idleTimeout
    labels:
      context: "$1"
      id: "$2"
  - pattern: org.eclipse.jetty.server<context=(.+), type=serverconnector$serverconnectormanager, id=(.+)><>selectorCount
    name: jetty_serverconnector_selectorCount
    labels:
      context: "$1"
      id: "$2"
  - pattern: org.eclipse.jetty.server<context=(.+), type=serverconnector$serverconnectormanager, id=(.+)><>connectTimeout
    name: jetty_serverconnector_connectTimeout
    labels:
      context: "$1"
      id: "$2"
  - pattern: org.eclipse.jetty.util.thread<type=queuedthreadpool, id=(.+)><>threadsPriority
    name: jetty_queuedthreadpool_threadsPriority
    labels:
      id: "$1"
  - pattern: org.eclipse.jetty.util.thread<type=queuedthreadpool, id=(.+)><>queueSize
    name: jetty_queuedthreadpool_queueSize
    labels:
      id: "$1"
  - pattern: org.eclipse.jetty.util.thread<type=queuedthreadpool, id=(.+)><>availableReservedThreads
    name: jetty_queuedthreadpool_availableReservedThreads
    labels:
      id: "$1"
  - pattern: org.eclipse.jetty.util.thread<type=queuedthreadpool, id=(.+)><>stopTimeout
    name: jetty_queuedthreadpool_stopTimeout
    labels:
      id: "$1"
  - pattern: org.eclipse.jetty.util.thread<type=queuedthreadpool, id=(.+)><>utilizedThreads
    name: jetty_queuedthreadpool_utilizedThreads
    labels:
      id: "$1"
  - pattern: org.eclipse.jetty.util.thread<type=queuedthreadpool, id=(.+)><>utilizationRate
    name: jetty_queuedthreadpool_utilizationRate
    labels:
      id: "$1"
  - pattern: org.eclipse.jetty.util.thread<type=queuedthreadpool, id=(.+)><>minThreads
    name: jetty_queuedthreadpool_minThreads
    labels:
      id: "$1"
  - pattern: org.eclipse.jetty.util.thread<type=queuedthreadpool, id=(.+)><>maxReservedThreads
    name: jetty_queuedthreadpool_maxReservedThreads
    labels:
      id: "$1"
  - pattern: org.eclipse.jetty.util.thread<type=queuedthreadpool, id=(.+)><>threads
    name: jetty_queuedthreadpool_threads
    labels:
      id: "$1"
  - pattern: org.eclipse.jetty.util.thread<type=queuedthreadpool, id=(.+)><>reservedThreads
    name: jetty_queuedthreadpool_reservedThreads
    labels:
      id: "$1"
  - pattern: org.eclipse.jetty.util.thread<type=queuedthreadpool, id=(.+)><>readyThreads
    name: jetty_queuedthreadpool_readyThreads
    labels:
      id: "$1"
  - pattern: org.eclipse.jetty.util.thread<type=queuedthreadpool, id=(.+)><>leasedThreads
    name: jetty_queuedthreadpool_leasedThreads
    labels:
      id: "$1"
  - pattern: org.eclipse.jetty.util.thread<type=queuedthreadpool, id=(.+)><>maxAvailableThreads
    name: jetty_queuedthreadpool_maxAvailableThreads
    labels:
      id: "$1"
  - pattern: org.eclipse.jetty.util.thread<type=queuedthreadpool, id=(.+)><>busyThreads
    name: jetty_queuedthreadpool_busyThreads
    labels:
      id: "$1"
  - pattern: org.eclipse.jetty.util.thread<type=queuedthreadpool, id=(.+)><>lowThreadsThreshold
    name: jetty_queuedthreadpool_lowThreadsThreshold
    labels:
      id: "$1"
  - pattern: org.eclipse.jetty.util.thread<type=queuedthreadpool, id=(.+)><>idleTimeout
    name: jetty_queuedthreadpool_idleTimeout
    labels:
      id: "$1"
  - pattern: org.eclipse.jetty.util.thread<type=queuedthreadpool, id=(.+)><>idleThreads
    name: jetty_queuedthreadpool_idleThreads
    labels:
      id: "$1"
  - pattern: org.eclipse.jetty.util.thread<type=queuedthreadpool, id=(.+)><>maxThreads
    name: jetty_queuedthreadpool_maxThreads
    labels:
      id: "$1"
  - pattern: org.eclipse.jetty.util.thread<type=queuedthreadpool, id=(.+)><>maxLeasedThreads
    name: jetty_queuedthreadpool_maxLeasedThreads
    labels:
      id: "$1"
  - pattern: org.eclipse.jetty.util.thread<type=reservedthreadexecutor, id=(.+)><>pending
    name: jetty_reservedthreadexecutor_pending
    labels:
      id: "$1"
  - pattern: org.eclipse.jetty.util.thread<type=reservedthreadexecutor, id=(.+)><>available
    name: jetty_reservedthreadexecutor_available
    labels:
      id: "$1"
  - pattern: org.eclipse.jetty.util.thread<type=reservedthreadexecutor, id=(.+)><>idleTimeoutMs
    name: jetty_reservedthreadexecutor_idleTimeoutMs
    labels:
      id: "$1"
  - pattern: org.eclipse.jetty.util.thread<type=reservedthreadexecutor, id=(.+)><>capacity
    name: jetty_reservedthreadexecutor_capacity
    labels:
      id: "$1"
  - pattern: org.eclipse.jetty.util.thread<type=threadpoolbudget, id=(.+)><>leasedThreads
    name: jetty_threadpoolbudget_leasedThreads
    labels:
      id: "$1"
  - pattern: org.eclipse.jetty.util.thread.strategy<context=(.+), type=eatwhatyoukill, id=(.+)><>stopTimeout
    name: jetty_eatwhatyoukill_stopTimeout
    labels:
      context: "$1"
      id: "$2"
  - pattern: org.eclipse.jetty.util.thread.strategy<context=(.+), type=eatwhatyoukill, id=(.+)><>pCTasksConsumed
    name: jetty_eatwhatyoukill_pCTasksConsumed
    labels:
      context: "$1"
      id: "$2"
  - pattern: org.eclipse.jetty.util.thread.strategy<context=(.+), type=eatwhatyoukill, id=(.+)><>pECTasksExecuted
    name: jetty_eatwhatyoukill_pECTasksExecuted
    labels:
      context: "$1"
      id: "$2"
  - pattern: org.eclipse.jetty.util.thread.strategy<context=(.+), type=eatwhatyoukill, id=(.+)><>ePCTasksConsumed
    name: jetty_eatwhatyoukill_ePCTasksConsumed
    labels:
      context: "$1"
      id: "$2"
  - pattern: org.eclipse.jetty.util.thread.strategy<context=(.+), type=eatwhatyoukill, id=(.+)><>pICTasksExecuted
    name: jetty_eatwhatyoukill_pICTasksExecuted
    labels:
      context: "$1"
      id: "$2"`;
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
