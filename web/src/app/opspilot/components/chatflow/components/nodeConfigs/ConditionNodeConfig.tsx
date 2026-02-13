import React from 'react';
import { Form, Select } from 'antd';
import type { ConditionNodeConfigProps } from './types';

const { Option } = Select;

export const ConditionNodeConfig: React.FC<ConditionNodeConfigProps> = ({
  t,
  nodes,
}) => {
  const triggerNodes = nodes.filter((n) => ['celery', 'restful', 'openai'].includes(n.data?.type || ''));

  return (
    <div className="mb-4">
      <h4 className="text-sm font-medium mb-3">{t('chatflow.nodeConfig.branchCondition')}</h4>
      <div className="grid grid-cols-3 gap-2">
        <Form.Item name="conditionField" rules={[{ required: true }]}>
          <Select placeholder={t('chatflow.nodeConfig.conditionField')}>
            <Option value="triggerType">{t('chatflow.nodeConfig.triggerType')}</Option>
          </Select>
        </Form.Item>
        <Form.Item name="conditionOperator" rules={[{ required: true }]}>
          <Select placeholder={t('chatflow.nodeConfig.conditionOperator')}>
            <Option value="equals">{t('chatflow.nodeConfig.equals')}</Option>
            <Option value="notEquals">{t('chatflow.nodeConfig.notEquals')}</Option>
          </Select>
        </Form.Item>
        <Form.Item name="conditionValue" rules={[{ required: true }]}>
          <Select placeholder={t('chatflow.nodeConfig.selectValue')}>
            {triggerNodes.map((n) => (
              <Option key={n.id} value={n.id}>{n.data.label}</Option>
            ))}
          </Select>
        </Form.Item>
      </div>
    </div>
  );
};
