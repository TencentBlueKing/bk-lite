import { IntegrationLogInstance } from '@/app/log/types/integration';
import { TableDataItem } from '@/app/log/types';
import { useWinlogbeatFormItems } from '../../common/winlogbeatFormItems';
import { cloneDeep } from 'lodash';
import { v4 as uuidv4 } from 'uuid';

export const useWinlogbeatConfig = () => {
  const commonFormItems = useWinlogbeatFormItems();
  const pluginConfig = {
    collector: 'Winlogbeat',
    collect_type: 'winlogbeat',
    icon: 'winlogbeat'
  };

  const defaultLevels = ['critical', 'error', 'warning'];

  return {
    getConfig: (extra: {
      dataSource?: IntegrationLogInstance[];
      mode: 'manual' | 'auto' | 'edit';
      onTableDataChange?: (data: IntegrationLogInstance[]) => void;
    }) => {
      const configs = {
        auto: {
          formItems: commonFormItems.getCommonFormItems({
            disabledFormItems: {},
            hiddenFormItems: {}
          }),
          initTableItems: {
            instance_id: `${pluginConfig.collector}-${
              pluginConfig.collect_type
            }-${uuidv4()}`
          },
          defaultForm: {
            security: {
              enabled: true,
              level: defaultLevels,
              event_id:
                '4624, 4625, 4634, 4648, 4672, 4688, 4720-4726, 4738, 4740'
            },
            system: {
              enabled: true,
              level: defaultLevels
            },
            application: {
              enabled: true,
              level: defaultLevels
            },
            sysmon: {
              enabled: false,
              level: ['critical', 'error', 'warning', 'info']
            },
            powershell: {
              enabled: false,
              level: ['critical', 'error', 'warning', 'info']
            },
            defender: {
              enabled: false,
              level: defaultLevels
            },
            task_scheduler: {
              enabled: false,
              level: defaultLevels
            },
            ignore_older: '72h'
          },
          columns: [],
          getParams: (row: IntegrationLogInstance, config: TableDataItem) => {
            const dataSource = cloneDeep(config.dataSource || []);

            // Flat structure
            const configData = {
              security_enabled: !!row.security?.enabled,
              security_level: (row.security?.level || []).join(','),
              security_event_id: row.security?.event_id || '',
              system_enabled: !!row.system?.enabled,
              system_level: (row.system?.level || []).join(','),
              application_enabled: !!row.application?.enabled,
              application_level: (row.application?.level || []).join(','),
              sysmon_enabled: !!row.sysmon?.enabled,
              sysmon_level: (row.sysmon?.level || []).join(','),
              powershell_enabled: !!row.powershell?.enabled,
              powershell_level: (row.powershell?.level || []).join(','),
              defender_enabled: !!row.defender?.enabled,
              defender_level: (row.defender?.level || []).join(','),
              task_scheduler_enabled: !!row.task_scheduler?.enabled,
              task_scheduler_level: (row.task_scheduler?.level || []).join(','),
              ignore_older: row.ignore_older || '72h'
            };

            return {
              collector: pluginConfig.collector,
              collect_type: pluginConfig.collect_type,
              configs: [configData],
              instances: dataSource.map((item: TableDataItem) => {
                return {
                  ...item,
                  node_ids: [item.node_ids].flat()
                };
              })
            };
          }
        },
        edit: {
          getFormItems: () => {
            return commonFormItems.getCommonFormItems({
              disabledFormItems: {},
              hiddenFormItems: {}
            });
          },
          getDefaultForm: (formData: TableDataItem) => {
            const content = formData?.child?.content || [];

            // 根据 name 查找配置
            const findConfig = (name: string) => {
              return content.find((item: any) => item.name === name);
            };

            const parseLevel = (levelStr: string) => {
              if (!levelStr) return [];
              return levelStr
                .split(',')
                .map((s: string) => s.trim())
                .filter(Boolean);
            };

            const securityConfig = findConfig('Security');
            const systemConfig = findConfig('System');
            const applicationConfig = findConfig('Application');
            const sysmonConfig = findConfig(
              'Microsoft-Windows-Sysmon/Operational'
            );
            const powershellConfig =
              findConfig('Microsoft-Windows-PowerShell/Operational') ||
              findConfig('Windows PowerShell');
            const defenderConfig = findConfig(
              'Microsoft-Windows-Windows Defender/Operational'
            );
            const taskSchedulerConfig = findConfig(
              'Microsoft-Windows-TaskScheduler/Operational'
            );

            // 获取 ignore_older（从任意一个配置中获取，因为所有配置共用同一个值）
            const ignoreOlder = content[0]?.ignore_older || '72h';

            return {
              security: {
                enabled: !!securityConfig,
                level: parseLevel(securityConfig?.level || ''),
                event_id: securityConfig?.event_id || ''
              },
              system: {
                enabled: !!systemConfig,
                level: parseLevel(systemConfig?.level || '')
              },
              application: {
                enabled: !!applicationConfig,
                level: parseLevel(applicationConfig?.level || '')
              },
              sysmon: {
                enabled: !!sysmonConfig,
                level: parseLevel(sysmonConfig?.level || '')
              },
              powershell: {
                enabled: !!powershellConfig,
                level: parseLevel(powershellConfig?.level || '')
              },
              defender: {
                enabled: !!defenderConfig,
                level: parseLevel(defenderConfig?.level || '')
              },
              task_scheduler: {
                enabled: !!taskSchedulerConfig,
                level: parseLevel(taskSchedulerConfig?.level || '')
              },
              ignore_older: ignoreOlder
            };
          },
          getParams: (formData: TableDataItem, configForm: TableDataItem) => {
            const originalChild = cloneDeep(configForm?.child || {});
            const originalContent = originalChild.content || [];

            // 日志名称映射
            const nameFormKeyMap: Record<string, string> = {
              Security: 'security',
              System: 'system',
              Application: 'application',
              'Microsoft-Windows-Sysmon/Operational': 'sysmon',
              'Microsoft-Windows-PowerShell/Operational': 'powershell',
              'Windows PowerShell': 'powershell',
              'Microsoft-Windows-Windows Defender/Operational': 'defender',
              'Microsoft-Windows-TaskScheduler/Operational': 'task_scheduler'
            };

            // 更新现有配置
            const updatedContent = originalContent.map((item: any) => {
              const formKey = nameFormKeyMap[item.name];
              if (!formKey) return item;

              const formConfig = formData[formKey];
              if (!formConfig) return item;

              const updatedItem: any = {
                ...item,
                ignore_older: formData.ignore_older || '72h',
                level: Array.isArray(formConfig.level)
                  ? formConfig.level.join(',')
                  : formConfig.level || ''
              };

              // Security 特殊处理 event_id
              if (
                item.name === 'Security' &&
                formConfig.event_id !== undefined
              ) {
                updatedItem.event_id = formConfig.event_id;
              }

              return updatedItem;
            });

            return {
              child: {
                ...originalChild,
                content: updatedContent
              }
            };
          }
        },
        manual: {
          defaultForm: {},
          formItems: commonFormItems.getCommonFormItems(),
          getParams: (row: TableDataItem) => {
            return {
              instance_name: row.instance_name,
              instance_id: row.instance_id
            };
          },
          getConfigText: () => '--'
        }
      };
      return {
        ...pluginConfig,
        ...configs[extra.mode]
      };
    }
  };
};
