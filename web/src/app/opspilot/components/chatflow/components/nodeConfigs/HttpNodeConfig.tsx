import React from 'react';
import { Form, Input, Select, InputNumber, Radio, Button } from 'antd';
import type { HttpNodeConfigProps } from './types';

const { Option } = Select;
const { TextArea } = Input;

export const HttpNodeConfig: React.FC<HttpNodeConfigProps> = ({
  t,
  paramRows,
  headerRows,
}) => {
  const renderKeyValueEditor = (rows: typeof paramRows, label: string) => {
    const { rows: items, addRow, removeRow, updateRow } = rows;
    return (
      <Form.Item label={label}>
        <div className="space-y-2">
          <div className="grid gap-2 text-sm text-gray-500 mb-1 grid-cols-[1fr_1fr_60px]">
            <span>{t('chatflow.nodeConfig.paramName')}</span>
            <span>{t('chatflow.nodeConfig.paramValue')}</span>
            <span>{t('chatflow.nodeConfig.operation')}</span>
          </div>
          {items.map((row, index) => (
            <div key={index} className="grid gap-2 items-center grid-cols-[1fr_1fr_60px]">
              <Input
                placeholder={t('chatflow.nodeConfig.enterParamName')}
                value={row.key}
                onChange={(e) => updateRow(index, 'key', e.target.value)}
              />
              <div className="flex items-center gap-1">
                <span className="text-xs bg-[var(--color-fill-1)] px-1 rounded">str</span>
                <Input
                  placeholder={t('chatflow.nodeConfig.enterOrReferenceParamValue')}
                  value={row.value}
                  onChange={(e) => updateRow(index, 'value', e.target.value)}
                />
              </div>
              <div className="flex gap-1">
                <Button type="text" size="small" icon="+" onClick={addRow} />
                <Button type="text" size="small" icon="-" onClick={() => removeRow(index)} disabled={items.length === 1} />
              </div>
            </div>
          ))}
        </div>
      </Form.Item>
    );
  };

  return (
    <>
      <Form.Item label="API" required>
        <div className="flex gap-2">
          <Form.Item name="method" noStyle rules={[{ required: true }]}>
            <Select style={{ width: 100 }}>
              {['GET', 'POST', 'PUT', 'DELETE'].map(m => <Option key={m} value={m}>{m}</Option>)}
            </Select>
          </Form.Item>
          <Form.Item name="url" noStyle rules={[{ required: true }]}>
            <Input placeholder={t('chatflow.nodeConfig.enterUrl')} className="flex-1" />
          </Form.Item>
        </div>
      </Form.Item>
      {renderKeyValueEditor(paramRows, t('chatflow.nodeConfig.requestParams'))}
      {renderKeyValueEditor(headerRows, t('chatflow.nodeConfig.requestHeaders'))}
      <Form.Item name="requestBody" label={t('chatflow.nodeConfig.requestBody')}>
        <TextArea rows={6} placeholder={t('chatflow.nodeConfig.requestBodyPlaceholder')} />
      </Form.Item>
      <Form.Item name="timeout" label={t('chatflow.nodeConfig.timeoutSettings')}>
        <InputNumber min={1} max={300} className="w-full" />
      </Form.Item>
      <Form.Item name="outputMode" label={t('chatflow.nodeConfig.outputMode')}>
        <Radio.Group>
          <Radio value="stream">{t('chatflow.nodeConfig.streamMode')}</Radio>
          <Radio value="once">{t('chatflow.nodeConfig.onceMode')}</Radio>
        </Radio.Group>
      </Form.Item>
    </>
  );
};
