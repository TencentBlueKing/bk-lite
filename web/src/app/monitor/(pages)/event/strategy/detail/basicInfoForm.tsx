import React from 'react';
import { Form, Input } from 'antd';
import { useTranslation } from '@/utils/i18n';
import GroupTreeSelector from '@/components/group-tree-select';
import { StrategyFields } from '@/app/monitor/types/event';

const BasicInfoForm: React.FC = () => {
  const { t } = useTranslation();

  return (
    <>
      <Form.Item<StrategyFields>
        label={
          <span className="w-[100px]">{t('monitor.events.strategyName')}</span>
        }
        name="name"
        rules={[{ required: true, message: t('common.required') }]}
      >
        <Input
          placeholder={t('monitor.events.strategyName')}
          className="w-[800px]"
        />
      </Form.Item>
      <Form.Item<StrategyFields>
        required
        label={
          <span className="w-[100px]">{t('monitor.events.alertName')}</span>
        }
      >
        <Form.Item
          name="alert_name"
          noStyle
          rules={[
            {
              required: true,
              message: t('common.required'),
            },
          ]}
        >
          <Input
            placeholder={t('monitor.events.alertName')}
            className="w-[800px]"
          />
        </Form.Item>
        <div className="text-[var(--color-text-3)] mt-[10px]">
          {t('monitor.events.alertNameTitle')}
        </div>
      </Form.Item>
      <Form.Item<StrategyFields>
        label={<span className="w-[100px]">{t('monitor.group')}</span>}
        name="organizations"
        rules={[{ required: true, message: t('common.required') }]}
      >
        <GroupTreeSelector
          style={{
            width: '800px',
            marginRight: '8px',
          }}
          placeholder={t('common.group')}
        />
      </Form.Item>
    </>
  );
};

export default BasicInfoForm;
