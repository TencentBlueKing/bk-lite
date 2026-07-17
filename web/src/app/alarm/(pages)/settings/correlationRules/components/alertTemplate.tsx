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
    <>
      <Form.Item
        name="md_alert_title"
        label={t('settings.correlation.alertTitle')}
        rules={[{ required: true, message: t('common.inputTip') }]}
      >
        <Input placeholder={t('settings.correlation.alertTitle')} />
      </Form.Item>

      <Form.Item
        name="md_alert_level"
        label={t('settings.correlation.alertLevel')}
        rules={[{ required: true, message: t('common.selectTip') }]}
      >
        <Select
          placeholder={t('common.selectTip')}
          options={levelList.map((item) => ({ value: String(item.level_id), label: item.level_display_name }))}
        />
      </Form.Item>

      <Form.Item
        name="md_alert_description"
        label={t('settings.correlation.alertDescription')}
        rules={[{ required: true, message: t('common.inputTip') }]}
      >
        <TextArea rows={4} placeholder={t('settings.correlation.alertDescription')} />
      </Form.Item>
    </>
  );
};

export default AlertTemplate;
