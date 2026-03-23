'use client';

import React from 'react';
import { Form, Input, InputNumber } from 'antd';
import type { FormInstance } from 'antd';
import { useTranslation } from '@/utils/i18n';

interface CheckPeriodProps {
  form: FormInstance;
}

const CheckPeriod: React.FC<CheckPeriodProps> = ({ form }) => {
  const { t } = useTranslation();

  return (
    <div className="space-y-4">
      <Form.Item
        name="md_cron_expr"
        rules={[{ required: true, message: t('common.selectTip') }]}
        className="mb-0"
      >
        <Input placeholder={t('settings.correlation.cronExpression')} />
      </Form.Item>

      <Form.Item
        name="md_grace_period"
        rules={[{ required: true, message: t('common.inputTip') }]}
        className="mb-0"
      >
        <InputNumber
          min={1}
          addonAfter={t('settings.correlation.min')}
          style={{ width: 180 }}
          placeholder={t('settings.correlation.gracePeriod')}
        />
      </Form.Item>
    </div>
  );
};

export default CheckPeriod;
