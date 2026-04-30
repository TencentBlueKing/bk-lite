'use client';

import React, { useEffect } from 'react';
import { Form, Input } from 'antd';
import { useTranslation } from '@/utils/i18n';
import { useUserInfoContext } from '@/context/userInfo';
import GroupTreeSelect from '@/components/group-tree-select';

interface StudioFormProps {
  form: any;
  initialValues?: any;
  visible: boolean;
}

const StudioForm: React.FC<StudioFormProps> = ({ form, initialValues, visible }) => {
  const { t } = useTranslation();
  const { selectedGroup } = useUserInfoContext();

  useEffect(() => {
    if (!visible) return;
    if (initialValues) {
      form.setFieldsValue(initialValues);
    } else {
      form.resetFields();
      form.setFieldsValue({ bot_type: 3 });
    }
  }, [initialValues, visible]);

  return (
    <Form form={form} layout="vertical" name="studio_form">
      <Form.Item name="bot_type" hidden initialValue={3}>
        <Input type="hidden" />
      </Form.Item>
      <Form.Item
        name="name"
        label={t('studio.form.name')}
        rules={[{ required: true, message: `${t('common.inputMsg')}${t('studio.form.name')}!` }]}
      >
        <Input placeholder={`${t('common.inputMsg')}${t('studio.form.name')}`} />
      </Form.Item>
      <Form.Item
        name="team"
        label={t('studio.form.group')}
        rules={[{ required: true, message: `${t('common.selectMsg')}${t('studio.form.group')}` }]}
        initialValue={selectedGroup ? [selectedGroup?.id] : []}
      >
        <GroupTreeSelect placeholder={`${t('common.selectMsg')}${t('studio.form.group')}`} />
      </Form.Item>
      <Form.Item
        name="introduction"
        label={t('studio.form.introduction')}
        rules={[{ required: true, message: `${t('common.inputMsg')}${t('studio.form.introduction')}!` }]}
      >
        <Input.TextArea rows={4} placeholder={`${t('common.inputMsg')}${t('studio.form.introduction')}`} />
      </Form.Item>
    </Form>
  );
};

export default StudioForm;
