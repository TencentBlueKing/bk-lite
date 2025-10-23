import React from 'react';
import { Form, Input } from 'antd';
import { useTranslation } from '@/utils/i18n';
import {
  InstNameConfig,
  IntegrationMonitoredObject,
} from '@/app/monitor/types/integration';
import { TableDataItem } from '@/app/monitor/types';
import { useSnmpCommonFormItems } from '../../common/snmpCommonFormItems';
import { cloneDeep } from 'lodash';
import {
  extractMongoDBUrl,
  replaceTemplate,
} from '@/app/monitor/utils/integration';

export const useFirewallSnmpPlugin = () => {
  const { t } = useTranslation();
  const snmpCommonFormItems = useSnmpCommonFormItems();
  const pluginConfig = {
    collect_type: 'snmp',
    config_type: ['firewall'],
    collector: 'Telegraf',
    instance_type: 'firewall',
    object_name: 'Firewall',
  };

  return {
    getPluginCfg: (extra: {
      dataSource?: IntegrationMonitoredObject[];
      mode: 'manual' | 'auto' | 'edit';
      onTableDataChange?: (data: IntegrationMonitoredObject[]) => void;
    }) => {
      const isEdit = extra.mode === 'edit';
      const disabledForm = {
        port: true,
        version: true,
        auth_password: true,
        priv_password: true,
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
          <Form.Item required label="IP">
            <Form.Item
              noStyle
              name="monitor_ip"
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
              {t('monitor.integrations.ipDes')}
            </span>
          </Form.Item>
          {snmpCommonFormItems.getCommonFormItems(disabledForm)}
        </>
      );

      const config = {
        auto: {
          formItems: snmpCommonFormItems.getCommonFormItems(),
          initTableItems: {
            ip: null,
          },
          defaultForm: {
            port: 161,
            version: 2,
            timeout: 10,
          },
          columns: [
            {
              title: 'IP',
              dataIndex: 'ip',
              key: 'ip',
              width: 200,
              render: (
                value: string,
                record: IntegrationMonitoredObject,
                index: number
              ) => (
                <Input
                  value={record.ip as string}
                  onChange={(e) =>
                    handleFieldAndInstNameChange(e, {
                      index,
                      field: 'ip',
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
                  timeout: row.timeout + 's',
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
                  instance_id: `${target?.cloud_region}_${pluginConfig.instance_type}_snmp_${item.ip}`,
                };
              }),
            };
          },
        },
        edit: {
          formItems,
          getDefaultForm: (formData: TableDataItem) => {
            const agent = formData?.child?.content?.config?.agents?.[0] || '';
            return {
              monitor_ip: extractMongoDBUrl(agent).host || '',
              port: extractMongoDBUrl(agent).port || '',
            };
          },
          getParams: (formData: TableDataItem, configForm: TableDataItem) => {
            const data = cloneDeep(formData);
            delete data.monitor_ip;
            delete data.port;
            Object.assign(configForm.child.content.config, data);
            return configForm;
          },
        },
        manual: {
          defaultForm: {
            port: 161,
            version: 2,
            timeout: 10,
          },
          formItems,
          getParams: (row: TableDataItem) => {
            const instanceId =
              pluginConfig.object_name + '-' + (row?.monitor_ip || '');
            return {
              instance_id: instanceId,
              instance_name: instanceId,
            };
          },
          getConfigText: (formData: { [key: string]: string | number }) => {
            const instanceId =
              pluginConfig.object_name + '-' + (formData?.monitor_ip || '');
            const configText: Record<string, string> = {
              v2: `[[inputs.snmp]]
                tags = { "instance_id"="$instance_id", "instance_type"="$instance_type", "collect_type"="$collect_type" }
                agents = ["udp://$monitor_ip:$port"]
                version = $version
                community= "$community"
                interval = "$intervals"
                timeout = "$timeouts" 
            
                [[inputs.snmp.field]]
                    oid = "RFC1213-MIB::sysUpTime.0"
                    name = "uptime"
            
                [[inputs.snmp.field]]
                    oid = "RFC1213-MIB::sysName.0"
                    name = "source"
                    is_tag = true
            
                [[inputs.snmp.table]]
                    oid = "IF-MIB::ifTable"
                    name = "interface"
                    inherit_tags = ["source"]
            
                [[inputs.snmp.table.field]]
                    oid = "IF-MIB::ifDescr"
                    name = "ifDescr"
                    is_tag = true`,
              v3: `[[inputs.snmp]]
                tags = { "instance_id"="$instance_id", "instance_type"="$instance_type", "collect_type"="snmp" }
                agents =["udp://$monitor_ip:$port"]
                version = $version
                timeout = "$timeouts" 
            
                sec_name = "$sec_name"
                sec_level = "$sec_level"
                auth_protocol = "$auth_protocol"
                auth_password = "$auth_password"
                priv_protocol = "$priv_protocol"
                priv_password = "$priv_password"
            
                [[inputs.snmp.field]]
                    oid = "RFC1213-MIB::sysUpTime.0"
                    name = "uptime"
            
                [[inputs.snmp.field]]
                    oid = "RFC1213-MIB::sysName.0"
                    name = "source"
                    is_tag = true
            
                [[inputs.snmp.table]]
                    oid = "IF-MIB::ifTable"
                    name = "interface"
                    inherit_tags = ["source"]
            
                [[inputs.snmp.table.field]]
                    oid = "IF-MIB::ifDescr"
                    name = "ifDescr"
                    is_tag = true`,
            };
            return replaceTemplate(configText[`v${formData.version}`] || '', {
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
