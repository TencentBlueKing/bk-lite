import React from 'react';
import { IntegrationLogInstance } from '@/app/log/types/integration';
import { TableDataItem } from '@/app/log/types';
import { useFileIntegrityAuditbeatFormItems } from '../../common/fileIntegrityAuditbeatFormItems';
import { cloneDeep } from 'lodash';
import { v4 as uuidv4 } from 'uuid';

export const useAuditbeatConfig = () => {
  const commonFormItems = useFileIntegrityAuditbeatFormItems();
  const pluginConfig = {
    collector: 'Auditbeat',
    collect_type: 'file_integrity',
    icon: 'shenjirizhi3'
  };

  return {
    getConfig: (extra: {
      dataSource?: IntegrationLogInstance[];
      mode: 'manual' | 'auto' | 'edit';
      onTableDataChange?: (data: IntegrationLogInstance[]) => void;
    }) => {
      const disabledForm = {
        monitor_paths: false
      };
      const formItems = (
        <>
          {commonFormItems.getCommonFormItems({
            disabledFormItems: disabledForm
          })}
        </>
      );
      const configs = {
        auto: {
          formItems: commonFormItems.getCommonFormItems(),
          initTableItems: {
            instance_id: `${pluginConfig.collector}-${
              pluginConfig.collect_type
            }-${uuidv4()}`
          },
          defaultForm: {
            monitor_paths: ['/etc/passwd', '/etc/shadow', '/etc/sudoers'],
            exclude_paths: [],
            hash_algorithm: 'sha256',
            recursive_monitor: false
          },
          columns: [],
          getParams: (row: IntegrationLogInstance, config: TableDataItem) => {
            const dataSource = cloneDeep(config.dataSource || []);
            const formDataCopy = cloneDeep(row);

            // 构建 content，只需要4个参数
            const content: Record<string, unknown> = {
              paths: formDataCopy.monitor_paths || [],
              exclude_files: formDataCopy.exclude_paths || [],
              hash_types: [formDataCopy.hash_algorithm || 'sha256'],
              recursive: formDataCopy.recursive_monitor || false
            };

            return {
              collector: pluginConfig.collector,
              collect_type: pluginConfig.collect_type,
              configs: [content],
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
          formItems,
          getDefaultForm: (formData: TableDataItem) => {
            const content = formData?.child?.content?.[0] || {};

            // 后端字段映射：paths -> monitor_paths, exclude_files -> exclude_paths
            // hash_types[0] -> hash_algorithm, recursive -> recursive_monitor
            return {
              monitor_paths: content.paths || [],
              exclude_paths: content.exclude_files || [],
              hash_algorithm: content.hash_types?.[0] || 'sha256',
              recursive_monitor: content.recursive ?? false
            };
          },
          getParams: (formData: TableDataItem, configForm: TableDataItem) => {
            const originalChild = cloneDeep(configForm?.child || {});
            const formDataCopy = cloneDeep(formData);

            return {
              child: {
                ...originalChild,
                content: {
                  paths: formDataCopy.monitor_paths || [],
                  exclude_files: formDataCopy.exclude_paths || [],
                  hash_types: [formDataCopy.hash_algorithm || 'sha256'],
                  recursive: formDataCopy.recursive_monitor || false
                }
              }
            };
          }
        },
        manual: {
          defaultForm: {},
          formItems,
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
