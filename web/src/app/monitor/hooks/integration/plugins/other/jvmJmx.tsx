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

export const useJvmJmx = () => {
  const { t } = useTranslation();
  const activeMQFormItems = useJmxCommonFormItems();
  const pluginConfig = {
    collect_type: 'jmx',
    config_type: ['jvm'],
    collector: 'JVM-JMX',
    instance_type: 'jvm',
    object_name: 'JVM',
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

# 白名单限制采集范围
whitelistObjectNames:
  - java.lang:type=Memory
  - java.lang:type=Threading
  - java.lang:type=OperatingSystem
  - java.nio:type=BufferPool,name=*
  - java.lang:type=GarbageCollector,name=*
  - java.lang:type=MemoryPool,name=*

rules:
  # 内存相关指标
  - pattern: java.lang<type=Memory><(\w+)MemoryUsage>(\w+)
    name: jvm_memory_usage_$2
    labels:
      type: $1

  # 线程相关指标
  - pattern: java.lang<type=Threading><>ThreadCount
    name: jvm_threads_count
  - pattern: java.lang<type=Threading><>DaemonThreadCount
    name: jvm_threads_daemon_count
  - pattern: java.lang<type=Threading><>PeakThreadCount
    name: jvm_threads_peak_count
  - pattern: java.lang<type=Threading><>TotalStartedThreadCount
    name: jvm_threads_total_started_count
  - pattern: java.lang<type=Threading><>CurrentThreadUserTime
    name: jvm_threads_current_user_time
    valueFactor: 0.001

  # 操作系统指标
  - pattern: java.lang<type=OperatingSystem><>FreePhysicalMemorySize
    name: jvm_os_memory_physical_free
  - pattern: java.lang<type=OperatingSystem><>TotalPhysicalMemorySize
    name: jvm_os_memory_physical_total
  - pattern: java.lang<type=OperatingSystem><>FreeSwapSpaceSize
    name: jvm_os_memory_swap_free
  - pattern: java.lang<type=OperatingSystem><>TotalSwapSpaceSize
    name: jvm_os_memory_swap_total
  - pattern: java.lang<type=OperatingSystem><>CommittedVirtualMemorySize
    name: jvm_os_memory_committed_virtual
  - pattern: java.lang<type=OperatingSystem><>AvailableProcessors
    name: jvm_os_available_processors
  - pattern: java.lang<type=OperatingSystem><>ProcessCpuTime
    name: jvm_os_processcputime_seconds
    valueFactor: 0.000000001

  # BufferPool 指标
  - pattern: java.nio<type=BufferPool, name=(.+)><>Count
    name: jvm_bufferpool_count
    labels:
      type: $1
  - pattern: java.nio<type=BufferPool, name=(.+)><>MemoryUsed
    name: jvm_bufferpool_memoryused
    labels:
      type: $1
  - pattern: java.nio<type=BufferPool, name=(.+)><>TotalCapacity
    name: jvm_bufferpool_totalcapacity
    labels:
      type: $1

  # GC 指标
  - pattern: java.lang<type=GarbageCollector, name=(.+)><>CollectionTime
    name: jvm_gc_collectiontime_seconds
    valueFactor: 0.001
    labels:
      type: $1
  - pattern: java.lang<type=GarbageCollector, name=(.+)><>CollectionCount
    name: jvm_gc_collectioncount
    labels:
      type: $1

  # MemoryPool 指标
  - pattern: java.lang<type=MemoryPool, name=(.+)><Usage>(\w+)
    name: jvm_memorypool_usage_$2
    labels:
      type: $1`;
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
