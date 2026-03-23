'use client';

import React from 'react';
import { Form, Input, Select } from 'antd';
import { useTranslation } from '@/utils/i18n';
import { useCommon } from '@/app/alarm/context/common';

const { TextArea } = Input;

const AlertTemplate: React.FC = () => {
  const { t } = useTranslation();
  const { levelList } = useCommon();
  const labelClassName = 'w-[56px] shrink-0 pr-2 pt-[5px] text-right text-sm text-gray-600';

  return (
    <div className="space-y-3">
      <div className="flex items-start">
        <div className={labelClassName}>{t('settings.correlation.alertTitle')}</div>
        <div className="w-full max-w-[660px]">
          <Form.Item
            name="md_alert_title"
            rules={[{ required: true, message: t('common.inputTip') }]}
            className="mb-0"
          >
            <Input placeholder={t('settings.correlation.alertTitle')} />
          </Form.Item>
        </div>
      </div>

      <div className="flex items-start">
        <div className={labelClassName}>{t('settings.correlation.alertLevel')}</div>
        <div className="w-full max-w-[660px]">
          <Form.Item
            name="md_alert_level"
            rules={[{ required: true, message: t('common.selectTip') }]}
            className="mb-0"
          >
            <Select
              placeholder={t('common.selectTip')}
              options={levelList.map((item) => ({ value: String(item.level_id), label: item.level_display_name }))}
            />
          </Form.Item>
        </div>
      </div>

      <div className="flex items-start">
        <div className={labelClassName}>{t('settings.correlation.alertDescription')}</div>
        <div className="w-full max-w-[660px]">
          <Form.Item
            name="md_alert_description"
            rules={[{ required: true, message: t('common.inputTip') }]}
            className="mb-0"
          >
            <TextArea rows={4} placeholder={t('settings.correlation.alertDescription')} />
          </Form.Item>
        </div>
      </div>
    </div>
  );
};

export default AlertTemplate;
