import React, { useState, useEffect, forwardRef, useImperativeHandle } from 'react';
import { Input, Form, InputNumber, Switch, TimePicker } from 'antd';
import { useTranslation } from '@/utils/i18n';
import type { FormInstance } from 'antd';
import dayjs from 'dayjs';
import customParseFormat from 'dayjs/plugin/customParseFormat';

// 添加 dayjs 插件支持
dayjs.extend(customParseFormat);

const { TextArea } = Input;

interface WebLinkFormProps {
  onFormChange: (isValid: boolean) => void;
  onFormDataChange: (data: { name: string, link: string, deep: number, sync_enabled: boolean, sync_time: string }) => void;
  initialData: { name: string, link: string, deep: number, sync_enabled?: boolean, sync_time?: string };
}

const WebLinkForm = forwardRef<FormInstance, WebLinkFormProps>(({ onFormChange, onFormDataChange, initialData }, ref) => {
  const { t } = useTranslation();
  const [form] = Form.useForm();
  const [formData, setFormData] = useState<{
    name: string;
    link: string;
    deep: number;
    sync_enabled: boolean;
    sync_time: string;
  }>({
    name: initialData.name,
    link: initialData.link,
    deep: initialData.deep,
    sync_enabled: initialData.sync_enabled ?? true,
    sync_time: initialData.sync_time ?? "00:00",
  });

  useImperativeHandle(ref, () => form);

  useEffect(() => {
    form.setFieldsValue({
      ...formData,
    });
  }, [formData, form]);

  useEffect(() => {
    const isValid = formData.name.trim() !== '' && formData.link.trim() !== '';
    onFormChange(isValid);
    onFormDataChange(formData);
  }, [formData, onFormChange, onFormDataChange]);

  const handleInputChange = (field: string, value: any) => {
    setFormData((prevData) => ({
      ...prevData,
      [field]: value,
    }));
  };

  const validateURL = (_: any, value: string) => {
    const normalizedValue = value?.trim();

    if (!normalizedValue) {
      return Promise.resolve();
    }

    try {
      const candidate = /^https?:\/\//i.test(normalizedValue) ? normalizedValue : `https://${normalizedValue}`;
      const parsedUrl = new URL(candidate);

      if (!["http:", "https:"].includes(parsedUrl.protocol) || !parsedUrl.hostname) {
        return Promise.reject(t('common.invalidURL'));
      }

      return Promise.resolve();
    } catch {
      return Promise.reject(t('common.invalidURL'));
    }
  };

  return (
    <div className="px-16">
      <Form
        form={form}
        labelCol={{ span: 3 }}
        wrapperCol={{ span: 20 }}
        onValuesChange={() => {
          const isValid = formData.name.trim() !== '' && formData.link.trim() !== '';
          onFormChange(isValid);
          onFormDataChange(formData);
        }}
        initialValues={formData} // 设置初始表单值
      >
        <Form.Item
          label={t('common.name')}
          name="name"
          rules={[{ required: true, message: t('common.inputRequired') }]}
        >
          <Input
            placeholder={`${t('common.inputMsg')}${t('common.name')}`}
            value={formData.name}
            onChange={(e) => handleInputChange('name', e.target.value)}
          />
        </Form.Item>
        <Form.Item
          label={t('knowledge.documents.link')}
          name="link"
          rules={[
            { required: true, message: t('common.inputRequired') },
            { validator: validateURL }
          ]}
        >
          <TextArea
            placeholder={`${t('common.inputMsg')}${t('knowledge.documents.link')}`}
            value={formData.link}
            onChange={(e) => handleInputChange('link', e.target.value)}
            rows={3}
          />
        </Form.Item>
        <Form.Item
          label={t('knowledge.documents.deep')}
          name="deep"
          tooltip={t('knowledge.documents.deepTip')}
        >
          <InputNumber
            min={1}
            value={formData.deep}
            style={{ width: '100%' }}
            onChange={(value) => {
              if (value !== null) {
                handleInputChange('deep', value);
              }
            }}
          />
        </Form.Item>
        <Form.Item
          label={t('knowledge.documents.syncEnabled')}
          name="sync_enabled"
          tooltip={t('knowledge.documents.syncEnabledTip')}
        >
          <Switch
            size="small"
            checked={formData.sync_enabled}
            onChange={(checked) => handleInputChange('sync_enabled', checked)}
          />
        </Form.Item>
        {formData.sync_enabled && (
          <Form.Item
            label={t('knowledge.documents.syncTime')}
            name="sync_time"
          >
            <div className="flex items-center flex-nowrap whitespace-nowrap text-gray-500">
              <span className="mr-2 flex-shrink-0">{t('knowledge.documents.everyday')}</span>
              <TimePicker
                format="HH:mm"
                placeholder={t('knowledge.documents.selectTime')}
                value={(() => {
                  if (!formData.sync_time) return undefined;
                  try {
                    const time = dayjs(formData.sync_time, 'HH:mm');
                    return time.isValid() ? time : undefined;
                  } catch {
                    return undefined;
                  }
                })()}
                onChange={(time) => {
                  const timeString = time ? time.format('HH:mm') : '00:00';
                  handleInputChange('sync_time', timeString);
                }}
                className="mx-2 min-w-[100px]"
              />
              <span className="ml-2 flex-shrink-0">{t('knowledge.documents.syncOnce')}</span>
            </div>
          </Form.Item>
        )}
      </Form>
    </div>
  );
});

WebLinkForm.displayName = 'WebLinkForm';

export default WebLinkForm;
