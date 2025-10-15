import React from 'react';
import { Form, Input } from 'antd';
import { useTranslation } from '@/utils/i18n';
import { IntegrationMonitoredObject } from '@/app/monitor/types/integration';
import { TableDataItem } from '@/app/monitor/types';
import { useTcpFormItems } from '../../common/tcpFormItems';
import { cloneDeep } from 'lodash';
import {
  extractVmvareUrl,
  replaceTemplate,
} from '@/app/monitor/utils/integration';

export const useTcpTelegraf = () => {
  const { t } = useTranslation();
  const tcpFormItems = useTcpFormItems();
  const pluginConfig = {
    collect_type: 'http',
    config_type: ['qcloud'],
    collector: 'Telegraf',
    instance_type: 'qcloud',
    object_name: 'TCP',
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

      const formItems = (
        <>
          {extra.mode === 'manual' && (
            <Form.Item required label={t('monitor.integrations.url')}>
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
                <Input className="w-[300px] mr-[10px]" />
              </Form.Item>
              <span className="text-[12px] text-[var(--color-text-3)]">
                {t('monitor.integrations.urlDes')}
              </span>
            </Form.Item>
          )}
          {tcpFormItems.getCommonFormItems(disabledForm)}
        </>
      );

      const config = {
        auto: {
          formItems: tcpFormItems.getCommonFormItems(),
          initTableItems: {},
          defaultForm: {},
          columns: [],
          getParams: (
            row: IntegrationMonitoredObject,
            config: TableDataItem
          ) => {
            const dataSource = cloneDeep(config.dataSource || []);
            row.custom_headers = {
              username: row.username,
              password: row.password,
            };
            delete row.username;
            delete row.password;
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
                  instance_id: item.instance_name,
                };
              }),
            };
          },
        },
        edit: {
          formItems,
          getDefaultForm: (formData: TableDataItem) => {
            const config = formData?.child?.content?.config || {};
            return {
              ...extractVmvareUrl(config),
              monitor_url: config.jmx_url || null,
            };
          },
          getParams: (
            row: IntegrationMonitoredObject,
            config: TableDataItem
          ) => {
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
            const configText = `[[inputs.prometheus]]
    urls = ["\${STARGAZER_URL}/api/monitor/qcloud/metrics"]
    interval = "$intervals"
    timeout = "30s"
    response_timeout = "30s"
    http_headers = { "username"="$username", "password"="$password" }
    [inputs.prometheus.tags]
        instance_id = "$instance_id"
        instance_type = "$instance_type"
        collect_type = "http"
        config_type = "prometheus"`;
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
