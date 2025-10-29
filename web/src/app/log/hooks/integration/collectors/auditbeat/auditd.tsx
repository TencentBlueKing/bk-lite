import React from 'react';
import { IntegrationLogInstance } from '@/app/log/types/integration';
import { TableDataItem } from '@/app/log/types';
import { useAuditdAuditbeatFormItems } from '../../common/auditdAuditbeatFormItems';
import { cloneDeep } from 'lodash';
import { v4 as uuidv4 } from 'uuid';

export const useAuditbeatConfig = () => {
  const commonFormItems = useAuditdAuditbeatFormItems();
  const pluginConfig = {
    collector: 'Auditbeat',
    collect_type: 'auditd',
    icon: 'shenjirizhi3',
  };

  return {
    getConfig: (extra: {
      dataSource?: IntegrationLogInstance[];
      mode: 'manual' | 'auto' | 'edit';
      onTableDataChange?: (data: IntegrationLogInstance[]) => void;
    }) => {
      const formItems = (
        <>
          {commonFormItems.getCommonFormItems({
            disabledFormItems: {},
            hiddenFormItems: {},
          })}
        </>
      );
      const configs = {
        auto: {
          formItems: commonFormItems.getCommonFormItems(),
          initTableItems: {
            instance_id: `${pluginConfig.collector}-${
              pluginConfig.collect_type
            }-${uuidv4()}`,
          },
          defaultForm: {},
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
            const auditRules =
              formData?.child?.content?.[0]?.audit_rules || null;
            const ruleCategories: string[] = [];
            if (auditRules.includes('identity')) {
              ruleCategories.push('security');
            }
            if (auditRules.includes('system')) {
              ruleCategories.push('system');
            }
            if (auditRules.includes('network')) {
              ruleCategories.push('network');
            }
            return {
              rule_categories: ruleCategories,
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
