import React from 'react';
import { Form, Select, Tooltip } from 'antd';
import { useTranslation } from '@/utils/i18n';
import { useRuleCategories } from '@/app/log/hooks/integration/common/other';
const { Option } = Select;

const useAuditdAuditbeatFormItems = () => {
  const { t } = useTranslation();
  const ruleCategoriesList = useRuleCategories();

  return {
    getCommonFormItems: (
      extra: {
        disabledFormItems: Record<string, boolean>;
        hiddenFormItems: Record<string, boolean>;
      } = {
        disabledFormItems: {},
        hiddenFormItems: {},
      }
    ) => {
      return (
        <>
          {!extra.hiddenFormItems.rule_categories && (
            <Form.Item
              name="rule_categories"
              label={t('log.integration.ruleCategories')}
              required
              tooltip={t('log.integration.ruleCategoriesDes')}
              rules={[
                {
                  required: true,
                  message: t('common.required'),
                },
              ]}
            >
              <Select
                mode="multiple"
                allowClear
                placeholder={t('log.integration.ruleCategories')}
                disabled={extra.disabledFormItems.rule_categories}
              >
                {ruleCategoriesList.map((item) => (
                  <Option key={item.id} value={item.id}>
                    <Tooltip title={item.label}>{item.name}</Tooltip>
                  </Option>
                ))}
              </Select>
            </Form.Item>
          )}
        </>
      );
    },
  };
};

export { useAuditdAuditbeatFormItems };
