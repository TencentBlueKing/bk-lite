import React, { useState, useEffect, forwardRef, useImperativeHandle } from 'react';
import { Input, Form, InputNumber } from 'antd';
import { useTranslation } from '@/utils/i18n';
import type { FormInstance } from 'antd';

const { TextArea } = Input;

interface WebLinkFormProps {
  onFormChange: (isValid: boolean) => void;
  onFormDataChange: (data: { name: string, link: string, deep: number }) => void;
  initialData: { name: string, link: string, deep: number };
}

const WebLinkForm = forwardRef<FormInstance, WebLinkFormProps>(({ onFormChange, onFormDataChange, initialData }, ref) => {
  const { t } = useTranslation();
  const [form] = Form.useForm();
  const [formData, setFormData] = useState<{ name: string; link: string; deep: number }>({
    name: initialData.name,
    link: initialData.link,
    deep: initialData.deep,
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
    const urlPattern = new RegExp('^(https?:\\/\\/)?' + // 协议
      '((([a-z\\d](([a-z\\d-]*[a-z\\d])?))\\.)+[a-z]{2,}|' + // 域名
      '((\\d{1,3}\\.){3}\\d{1,3}))' + // 或者 IP 地址
      '(\\:\\d+)?(\\/[-a-z\\d%_.~+]*)*' + // 端口和路径
      '(\\?[;&a-z\\d%_.~+=-]*)?' + // 查询字符串
      '(\\#[-a-z\\d_]*)?$', 'i'); // 片段定位符
    return urlPattern.test(value) ? Promise.resolve() : Promise.reject(t('common.invalidURL'));
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
          label={t('knowledge.form.name')}
          name="name"
          rules={[{ required: true, message: t('common.inputRequired') }]}
        >
          <Input
            placeholder={`${t('common.inputMsg')}${t('knowledge.form.name')}`}
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
      </Form>
    </div>
  );
});

WebLinkForm.displayName = 'WebLinkForm';

export default WebLinkForm;