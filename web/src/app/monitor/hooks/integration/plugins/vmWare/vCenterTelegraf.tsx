import React from 'react';
import { Form, Input } from 'antd';
import { useTranslation } from '@/utils/i18n';
import {
  InstNameConfig,
  IntegrationMonitoredObject,
} from '@/app/monitor/types/integration';
import { TableDataItem } from '@/app/monitor/types';
import { useVCenterFormItems } from '../../common/vCenterFormItems';
import { cloneDeep } from 'lodash';
import {
  extractVmvareUrl,
  replaceTemplate,
} from '@/app/monitor/utils/integration';

export const useVCenterTelegraf = () => {
  const { t } = useTranslation();
  const vCenterFormItems = useVCenterFormItems();
  const pluginConfig = {
    collect_type: 'http',
    config_type: ['vmware'],
    collector: 'Telegraf',
    instance_type: 'vmware',
    object_name: 'vCenter',
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

      const formItems = (
        <>
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
          {vCenterFormItems.getCommonFormItems(disabledForm)}
        </>
      );

      const config = {
        auto: {
          formItems: vCenterFormItems.getCommonFormItems(),
          initTableItems: {
            host: null,
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
                const target: TableDataItem | undefined = config.nodeList.find(
                  (tex: IntegrationMonitoredObject) => item.node_ids === tex.id
                );
                return {
                  ...item,
                  node_ids: [item.node_ids].flat(),
                  instance_type: pluginConfig.instance_type,
                  instance_id: `${target?.cloud_region}_${pluginConfig.instance_type}_${item.host}`,
                };
              }),
            };
          },
        },
        edit: {
          formItems,
          getDefaultForm: (formData: TableDataItem) => {
            const config = formData?.child?.content?.config || {};
            return extractVmvareUrl(config);
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
            const instanceId = `vc-${row.host}`;
            return {
              instance_id: instanceId,
              instance_name: instanceId,
            };
          },
          getConfigText: (formData: { [key: string]: string | number }) => {
            const configText = `[[inputs.prometheus]]
    urls = ["\${STARGAZER_URL}/api/monitor/vmware/metrics"]
    interval = "$intervals"
    timeout = "30s"
    response_timeout = "30s"
    http_headers = { "username"="$username", "password"="$password", "host"="$host" }
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
