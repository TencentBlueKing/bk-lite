'use client';

import React, {useEffect, useState} from 'react';
import {Alert, Button, Form, Input, InputNumber, message, Select, Spin} from 'antd';
import {CheckCircleOutlined, CloseCircleOutlined} from '@ant-design/icons';
import {useTranslation} from '@/utils/i18n';
import {EngineConfigField, EngineConfigSchema, StorageType, useMemoryApi,} from '@/app/opspilot/api/memory';

const { TextArea } = Input;

interface EngineConfigFormProps {
  engineType: StorageType;
  value?: Record<string, unknown>;
  onChange?: (value: Record<string, unknown>) => void;
  disabled?: boolean;
}

/**
 * Dynamic form for memory engine configuration.
 * Renders form fields based on engine schema from backend API.
 */
export const EngineConfigForm: React.FC<EngineConfigFormProps> = ({
  engineType,
  value = {},
  onChange,
  disabled = false,
}) => {
  const { t } = useTranslation();
  const { fetchEngineSchema, testEngineConnection } = useMemoryApi();
  const [form] = Form.useForm();

  const [loading, setLoading] = useState(false);
  const [schema, setSchema] = useState<EngineConfigSchema | null>(null);
  const [testing, setTesting] = useState(false);
  const [testResult, setTestResult] = useState<{ success: boolean; message: string } | null>(null);

  // Load schema when engine type changes
  useEffect(() => {
    if (engineType === 'local') {
      // Local engine has no config
      setSchema(null);
      return;
    }

    setLoading(true);
    setTestResult(null);
    fetchEngineSchema(engineType)
      .then((data) => {
        setSchema(data);
      })
      .catch((err) => {
        console.error('Failed to fetch engine schema:', err);
        message.error(t('common.fetchFailed'));
      })
      .finally(() => {
        setLoading(false);
      });
  }, [engineType, fetchEngineSchema, t]);

  // Sync form values with external value prop
  useEffect(() => {
    if (value && Object.keys(value).length > 0) {
      form.setFieldsValue(value);
    }
  }, [value, form]);

  const handleValuesChange = (_: unknown, allValues: Record<string, unknown>) => {
    onChange?.(allValues);
  };

  const handleTestConnection = async () => {
    try {
      const values = await form.validateFields();
      setTesting(true);
      setTestResult(null);

      const result = await testEngineConnection(engineType, values);
      setTestResult(result);

      if (result.success) {
        message.success(t('memory.testConnectionSuccess'));
      } else {
        message.error(`${t('memory.testConnectionFailed')}: ${result.message}`);
      }
    } catch (err) {
      console.error('Test connection failed:', err);
    } finally {
      setTesting(false);
    }
  };

  const renderField = (field: EngineConfigField) => {
    const commonProps = {
      disabled,
      placeholder: field.placeholder,
    };

    switch (field.type) {
      case 'password':
        return <Input.Password {...commonProps} />;
      case 'number':
        return <InputNumber {...commonProps} style={{ width: '100%' }} />;
      case 'select':
        return (
          <Select {...commonProps}>
            {field.options?.map((opt) => (
              <Select.Option key={opt.value} value={opt.value}>
                {opt.label}
              </Select.Option>
            ))}
          </Select>
        );
      case 'json':
        return <TextArea {...commonProps} rows={4} />;
      case 'text':
      default:
        return <Input {...commonProps} />;
    }
  };

  // Local engine has no configuration
  if (engineType === 'local') {
    return (
      <Alert
        type="info"
        message={t('memory.storageTypeLocalDesc')}
        showIcon
      />
    );
  }

  if (loading) {
    return (
      <div className="flex justify-center py-8">
        <Spin />
      </div>
    );
  }

  if (!schema) {
    return null;
  }

  return (
    <div className="space-y-4">
      <Form
        form={form}
        layout="vertical"
        onValuesChange={handleValuesChange}
        initialValues={value}
      >
        {schema.fields.map((field) => (
          <Form.Item
            key={field.name}
            name={field.name}
            label={field.label}
            rules={[
              {
                required: field.required,
                message: `${t('common.inputMsg')}${field.label}`,
              },
            ]}
            initialValue={field.default}
          >
            {renderField(field)}
          </Form.Item>
        ))}
      </Form>

      {/* Test Connection Button */}
      <div className="flex items-center gap-4">
        <Button
          onClick={handleTestConnection}
          loading={testing}
          disabled={disabled}
        >
          {t('memory.testConnection')}
        </Button>

        {testResult && (
          <span className={`flex items-center gap-1 ${testResult.success ? 'text-green-600' : 'text-red-600'}`}>
            {testResult.success ? (
              <>
                <CheckCircleOutlined />
                {t('memory.testConnectionSuccess')}
              </>
            ) : (
              <>
                <CloseCircleOutlined />
                {testResult.message}
              </>
            )}
          </span>
        )}
      </div>
    </div>
  );
};

export default EngineConfigForm;
