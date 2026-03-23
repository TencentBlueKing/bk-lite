'use client';

import React from 'react';
import { Form, Input, Select } from 'antd';
import { useTranslation } from '@/utils/i18n';
import { useCommon } from '@/app/alarm/context/common';

const { TextArea } = Input;

const AlertTemplate: React.FC = () => {
  const { t } = useTranslation();
  const { levelList } = useCommon();

  return (
    <div className="space-y-4">
      <Form.Item
        name="md_alert_title"
        rules={[{ required: true, message: t('common.inputTip') }]}
        className="mb-0"
      >
        <Input placeholder={t('settings.correlation.alertTitle')} />
      </Form.Item>
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
      <Form.Item
        name="md_alert_description"
        rules={[{ required: true, message: t('common.inputTip') }]}
        className="mb-0"
      >
        <TextArea rows={4} placeholder={t('settings.correlation.alertDescription')} />
      </Form.Item>
    </div>
  );
};

export default AlertTemplate;
