'use client';

import React from 'react';
import { Form, InputNumber, Tooltip } from 'antd';
import { QuestionCircleOutlined } from '@ant-design/icons';
import { useTranslation } from '@/utils/i18n';
import CronPresetInput from './cronPresetInput';
import { isValidCronExpression } from './cronPresetUtils';

const CheckPeriod: React.FC = () => {
  const { t } = useTranslation();
  const labelClassName = 'w-[100px] shrink-0 pr-2 pt-[5px] text-right text-sm text-gray-600';

  return (
    <div className="space-y-3">
      <Form.Item
        name="md_cron_expr"
        rules={[
          { required: true, message: t('common.selectTip') },
          {
            validator: async (_, value?: string) => {
              if (!value) return;
              if (!isValidCronExpression(value)) {
                throw new Error(t('settings.correlation.cronDesc.invalid'));
              }
            },
          },
        ]}
        noStyle
      >
        <CronPresetInput />
      </Form.Item>

      <div className="flex items-start">
        <div className={labelClassName}>
          <span className="inline-flex items-center">
            {t('settings.correlation.gracePeriod')}
            <Tooltip title={t('settings.correlation.gracePeriodTip')}>
              <QuestionCircleOutlined className="ml-1 cursor-help text-xs text-gray-400" />
            </Tooltip>
          </span>
        </div>
        <div className="w-[180px]">
          <Form.Item
            name="md_grace_period"
            rules={[{ required: true, message: t('common.inputTip') }]}
            className="mb-0"
          >
            <InputNumber min={1} addonAfter={t('settings.correlation.min')} className="w-full" />
          </Form.Item>
        </div>
      </div>
    </div>
  );
};

export default CheckPeriod;
