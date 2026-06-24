import React from 'react';
import { Form, Input } from 'antd';
import { useTranslation } from '@/utils/i18n';
import GroupTreeSelector from '@/components/group-tree-select';
import { StrategyFields } from '@/app/log/types/event';

interface BasicInfoFormProps {
  policyType?: 'keyword' | 'aggregate';
}

const BasicInfoForm: React.FC<BasicInfoFormProps> = ({ policyType }) => {
  const { t } = useTranslation();
  const lockedPolicyType = policyType || 'keyword';

  return (
    <>
      <Form.Item<StrategyFields>
        label={<span className="w-[100px]">{t('log.event.strategyName')}</span>}
        name="name"
        rules={[{ required: true, message: t('common.required') }]}
      >
        <Input placeholder={t('log.event.strategyName')} className="w-full" />
      </Form.Item>
      <Form.Item<StrategyFields>
        required
        label={<span className="w-[100px]">{t('log.event.alertName')}</span>}
      >
        <Form.Item
          name="alert_name"
          noStyle
          rules={[
            {
              required: true,
              message: t('common.required')
            }
          ]}
        >
          <Input placeholder={t('log.event.alertName')} className="w-full" />
        </Form.Item>
        <div className="text-[var(--color-text-3)] mt-[10px]">
          {lockedPolicyType === 'aggregate'
            ? t('log.event.alertNameTitle')
            : t('log.event.keyWordAlertNameTitle')}
        </div>
      </Form.Item>
      <Form.Item<StrategyFields>
        label={<span className="w-[100px]">{t('common.organizations')}</span>}
        name="organizations"
        rules={[{ required: true, message: t('common.required') }]}
      >
        <GroupTreeSelector
          style={{
            width: '100%',
            marginRight: '8px'
          }}
          placeholder={t('common.organizations')}
        />
      </Form.Item>
    </>
  );
};

export default BasicInfoForm;
