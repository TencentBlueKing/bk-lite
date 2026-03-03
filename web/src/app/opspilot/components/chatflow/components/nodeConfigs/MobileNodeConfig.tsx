import React from 'react';
import { Form, Input, Select } from 'antd';
import type { MobileNodeConfigProps } from './types';

const { TextArea } = Input;

export const MobileNodeConfig: React.FC<MobileNodeConfigProps> = ({ t }) => {
  return (
    <>
      <Form.Item
        name="appName"
        label={t('chatflow.nodeConfig.appName')}
        rules={[{
          required: true,
          message: t('chatflow.nodeConfig.pleaseEnterAppName'),
          whitespace: true
        }]}
      >
        <Input placeholder={t('chatflow.nodeConfig.enterAppName')} />
      </Form.Item>
      <Form.Item
        name="appTags"
        label={t('chatflow.nodeConfig.appTags')}
        rules={[{
          required: true,
          message: t('chatflow.nodeConfig.pleaseSelectAppTags'),
          type: 'array',
          min: 1
        }]}
      >
        <Select
          mode="multiple"
          placeholder={t('chatflow.nodeConfig.selectAppTags')}
          options={[
            { label: t('chatflow.nodeConfig.appTagRoutineOps'), value: 'routine_ops' },
            { label: t('chatflow.nodeConfig.appTagMonitorAlarm'), value: 'monitor_alarm' },
            { label: t('chatflow.nodeConfig.appTagAutomation'), value: 'automation' },
            { label: t('chatflow.nodeConfig.appTagSecurityAudit'), value: 'security_audit' },
            { label: t('chatflow.nodeConfig.appTagPerformanceAnalysis'), value: 'performance_analysis' },
            { label: t('chatflow.nodeConfig.appTagOpsPlanning'), value: 'ops_planning' },
          ]}
        />
      </Form.Item>
      <Form.Item
        name="appDescription"
        label={t('chatflow.nodeConfig.appDescription')}
        rules={[{
          required: true,
          message: t('chatflow.nodeConfig.pleaseEnterAppDescription'),
          whitespace: true
        }]}
      >
        <TextArea
          rows={4}
          placeholder={t('chatflow.nodeConfig.enterAppDescription')}
        />
      </Form.Item>
    </>
  );
};
