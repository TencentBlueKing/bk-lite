import React from 'react';
import { Form, Input } from 'antd';
import { useTranslation } from '@/utils/i18n';
import GroupTreeSelector from '@/components/group-tree-select';
import { StrategyFields } from '@/app/log/types/event';

const BasicInfoForm: React.FC = () => {
  const { t } = useTranslation();

  return (
    <>
      <Form.Item<StrategyFields>
        label={<span className="w-[100px]">{t('log.event.strategyName')}</span>}
        name="name"
        rules={[{ required: true, message: t('common.required') }]}
      >
        <Input
          placeholder={t('log.event.strategyName')}
          className="w-[800px]"
        />
      </Form.Item>
      <Form.Item<StrategyFields>
        label={<span className="w-[100px]">{t('common.organizations')}</span>}
        name="organizations"
        rules={[{ required: true, message: t('common.required') }]}
      >
        <GroupTreeSelector
          style={{
            width: '800px',
            marginRight: '8px',
          }}
          placeholder={t('common.organizations')}
        />
      </Form.Item>
    </>
  );
};

export default BasicInfoForm;
