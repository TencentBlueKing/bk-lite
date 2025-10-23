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
    icon: 'shenjirizhi3',
  };

  return {
    getConfig: (extra: {
      dataSource?: IntegrationLogInstance[];
      mode: 'manual' | 'auto' | 'edit';
      onTableDataChange?: (data: IntegrationLogInstance[]) => void;
    }) => {
      const formItems = <>{commonFormItems.getCommonFormItems()}</>;
      const configs = {
        auto: {
          formItems: commonFormItems.getCommonFormItems(),
          initTableItems: {
            instance_id: `${pluginConfig.collector}-${
              pluginConfig.collect_type
            }-${uuidv4()}`,
          },
          defaultForm: {
            paths: ['/bin', '/usr/bin', '/sbin', '/usr/sbin', '/etc'],
          },
          columns: [],
          getParams: (row: IntegrationLogInstance, config: TableDataItem) => {
            const dataSource = cloneDeep(config.dataSource || []);
            return {
              collector: pluginConfig.collector,
              collect_type: pluginConfig.collect_type,
              configs: [row],
              instances: dataSource.map((item: TableDataItem) => {
                return {
                  ...item,
                  node_ids: [item.node_ids].flat(),
                };
              }),
            };
          },
        },
        edit: {
          formItems,
          getDefaultForm: (formData: TableDataItem) => {
            const paths = formData?.child?.content?.[0]?.paths || null;
            return {
              paths,
            };
          },
          getParams: (formData: TableDataItem, configForm: TableDataItem) => {
            return {
              child: {
                id: configForm.child.id,
                content_data: formData,
              },
            };
          },
        },
        manual: {
          defaultForm: {},
          formItems,
          getParams: (row: TableDataItem) => {
            return {
              instance_name: row.instance_name,
              instance_id: row.instance_id,
            };
          },
          getConfigText: () => '--',
        },
      };
      return {
        ...pluginConfig,
        ...configs[extra.mode],
      };
    },
  };
};
