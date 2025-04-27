'use client';

import React, { useState, useRef, useEffect } from 'react';
import useApiClient from '@/utils/request';
import type { FormInstance } from 'antd';
import { Drawer, Button, Form, Input, Select, message } from 'antd';
import { useTranslation } from '@/utils/i18n';

interface DeviceType {
  key: string;
  label: string;
}

interface OidDetail {
  oid: string;
  device_type: string | undefined;
  brand: string;
  model: string;
  id?: string;
}

interface OperateOidProps {
  deviceTypeList: DeviceType[];
  visible: boolean;
  data: {
    id?: string;
    model: string;
    brand: string;
    device_type: string;
    oid?: string;
  } | null;
  onCancel: () => void;
  onOk: () => void;
}

const INITIAL_FORM_DATA: OidDetail = {
  oid: '',
  device_type: undefined,
  brand: '',
  model: '',
};

const OperateOid: React.FC<OperateOidProps> = ({
  deviceTypeList,
  visible,
  data,
  onCancel,
  onOk,
}) => {
  const { t } = useTranslation();
  const { post, put } = useApiClient();
  const [loading, setLoading] = useState<boolean>(false);
  const [formData, setFormData] = useState<OidDetail>(INITIAL_FORM_DATA);
  const [currentType, setCurrentType] = useState<string>('add');
  const formRef = useRef<FormInstance>(null);

  useEffect(() => {
    if (visible) {
      formRef.current?.resetFields();

      if (data) {
        setCurrentType('edit');
        const formattedData: OidDetail = {
          oid: data.oid || '',
          device_type: data.device_type,
          brand: data.brand,
          model: data.model,
          id: data.id,
        };
        setTimeout(() => {
          formRef.current?.setFieldsValue(formattedData);
        }, 0);
        setFormData(formattedData);
      } else {
        setCurrentType('add');
        formRef.current?.setFieldsValue(INITIAL_FORM_DATA);
        setFormData(INITIAL_FORM_DATA);
      }
    }
  }, [visible, data]);

  const cancel = () => {
    formRef.current?.resetFields();
    setFormData(INITIAL_FORM_DATA);
    setLoading(false);
    onCancel();
  };

  const confirm = async () => {
    try {
      const values = await formRef.current?.validateFields();
      setLoading(true);

      const params = { ...values };
      try {
        if (currentType === 'add') {
          await post('/cmdb/api/oid/', params);
        } else {
          await put(`/cmdb/api/oid/${formData.id}/`, params);
        }
        message.success(
          t(
            `${currentType === 'add' ? 'successfullyAdded' : 'successfullyModified'}`
          )
        );
        onOk();
      } catch {
        message.error('操作失败');
      }
    } catch {
    } finally {
      setLoading(false);
    }
  };

  return (
    <Drawer
      title={`${t(currentType === 'add' ? 'common.addNew' : 'common.edit')}${t('OidLibrary.Mapping')}`}
      width={600}
      open={visible}
      onClose={cancel}
      footer={
        <div style={{ textAlign: 'left' }}>
          <Button
            type="primary"
            style={{ marginRight: '8px' }}
            loading={loading}
            onClick={confirm}
          >
            {t('confirm')}
          </Button>
          <Button onClick={cancel}>{t('cancel')}</Button>
        </div>
      }
    >
      <Form
        ref={formRef}
        labelCol={{ span: 5 }}
        initialValues={formData}
        onValuesChange={(changedValues, values) => setFormData(values)}
      >
        <Form.Item
          name="device_type"
          label={t('OidLibrary.deviceType')}
          rules={[{ required: true, message: t('common.selectMsg') }]}
        >
          <Select placeholder={t('common.selectMsg')}>
            {deviceTypeList.map((option) => (
              <Select.Option key={option.key} value={option.key}>
                {option.label}
              </Select.Option>
            ))}
          </Select>
        </Form.Item>
        <Form.Item
          name="oid"
          label="sysObjectID"
          rules={[{ required: true, message: t('common.inputMsg') }]}
        >
          <Input allowClear placeholder={t('common.inputMsg')} />
        </Form.Item>
        <Form.Item
          name="brand"
          label={t('OidLibrary.brand')}
          rules={[{ required: true, message: t('common.inputMsg') }]}
        >
          <Input allowClear placeholder={t('common.inputMsg')} />
        </Form.Item>
        <Form.Item
          name="model"
          label={t('OidLibrary.model')}
          rules={[{ required: true, message: t('common.inputMsg') }]}
        >
          <Input allowClear placeholder={t('common.inputMsg')} />
        </Form.Item>
      </Form>
    </Drawer>
  );
};

export default OperateOid;
