import React from 'react';
import { Form, Select } from 'antd';
import { InfoCircleOutlined } from '@ant-design/icons';
import { TimeListField, MonthDayPicker, CronEditor } from '../index';
import type { CeleryNodeConfigProps } from './types';

const { Option } = Select;

export const CeleryNodeConfig: React.FC<CeleryNodeConfigProps> = ({
  t,
  frequency,
  onFrequencyChange,
}) => {
  return (
    <>
      <Form.Item name="frequency" label={t('chatflow.nodeConfig.triggerFrequency')} rules={[{ required: true }]}>
        <Select placeholder={t('chatflow.nodeConfig.pleaseSelectTriggerFrequency')} onChange={onFrequencyChange}>
          <Option value="daily">{t('chatflow.daily')}</Option>
          <Option value="weekly">{t('chatflow.weekly')}</Option>
          <Option value="monthly">{t('chatflow.monthly')}</Option>
          <Option value="cron">{t('chatflow.cron')}</Option>
        </Select>
      </Form.Item>

      {frequency === 'daily' && (
        <>
          <div className="mb-4 p-3 bg-blue-50 border border-blue-200 rounded-md flex items-start gap-2">
            <InfoCircleOutlined className="text-blue-500 mt-0.5" />
            <span className="text-sm text-blue-600">
              {t('chatflow.nodeConfig.dailyTip')}
            </span>
          </div>
          <Form.Item name="times" label={t('chatflow.nodeConfig.triggerTime')} rules={[{ required: true }]}>
            <TimeListField />
          </Form.Item>
        </>
      )}

      {frequency === 'weekly' && (
        <>
          <Form.Item name="weekdays" label={t('chatflow.nodeConfig.selectWeekdays')} rules={[{ required: true }]}>
            <Select
              mode="multiple"
              placeholder={t('chatflow.nodeConfig.pleaseSelectWeekdays')}
              options={[
                { label: t('chatflow.nodeConfig.monday'), value: 1 },
                { label: t('chatflow.nodeConfig.tuesday'), value: 2 },
                { label: t('chatflow.nodeConfig.wednesday'), value: 3 },
                { label: t('chatflow.nodeConfig.thursday'), value: 4 },
                { label: t('chatflow.nodeConfig.friday'), value: 5 },
                { label: t('chatflow.nodeConfig.saturday'), value: 6 },
                { label: t('chatflow.nodeConfig.sunday'), value: 0 },
              ]}
            />
          </Form.Item>
          <Form.Item name="times" label={t('chatflow.nodeConfig.triggerTime')} rules={[{ required: true }]}>
            <TimeListField />
          </Form.Item>
        </>
      )}

      {frequency === 'monthly' && (
        <>
          <Form.Item name="monthDay" label={t('chatflow.nodeConfig.triggerDate')} rules={[{ required: true }]}>
            <MonthDayPicker />
          </Form.Item>
          <Form.Item name="times" label={t('chatflow.nodeConfig.triggerTime')} rules={[{ required: true }]}>
            <TimeListField />
          </Form.Item>
        </>
      )}

      {frequency === 'cron' && (
        <Form.Item name="cron" rules={[{ required: true }]}>
          <CronEditor />
        </Form.Item>
      )}
    </>
  );
};
