'use client';

import React, { useEffect } from 'react';
import { Form, Input } from 'antd';
import { useTranslation } from '@/utils/i18n';
import { useUserInfoContext } from '@/context/userInfo';
import GroupTreeSelect from '@/components/group-tree-select';

// 当前只有单一智能体类型，新建技能统一使用 skill_type = 1
const DEFAULT_SKILL_TYPE = 1;

interface SkillFormProps {
  form: any;
  initialValues?: any;
  visible: boolean;
}

const SkillForm: React.FC<SkillFormProps> = ({ form, initialValues, visible }) => {
  const { t } = useTranslation();
  const { selectedGroup } = useUserInfoContext();

  useEffect(() => {
    if (!visible) return;
    if (initialValues) {
      form.setFieldsValue(initialValues);
    } else {
      form.resetFields();
      form.setFieldsValue({ skill_type: DEFAULT_SKILL_TYPE });
    }
  }, [initialValues, visible]);

  return (
    <Form form={form} layout="vertical" name="skill_form">
      <Form.Item name="skill_type" initialValue={DEFAULT_SKILL_TYPE} hidden>
        <Input type="hidden" />
      </Form.Item>
      <Form.Item
        name="name"
        label={t('skill.form.name')}
        rules={[{ required: true, message: `${t('common.inputMsg')}${t('skill.form.name')}!` }]}
      >
        <Input placeholder={`${t('common.inputMsg')}${t('skill.form.name')}`} />
      </Form.Item>
      <Form.Item
        name="team"
        label={t('skill.form.group')}
        rules={[{ required: true, message: `${t('common.selectMsg')}${t('skill.form.group')}` }]}
        initialValue={selectedGroup ? [selectedGroup?.id] : []}
      >
        <GroupTreeSelect placeholder={`${t('common.selectMsg')}${t('skill.form.group')}`} />
      </Form.Item>
      <Form.Item
        name="introduction"
        label={t('skill.form.introduction')}
        rules={[{ required: true, message: `${t('common.inputMsg')}${t('skill.form.introduction')}!` }]}
      >
        <Input.TextArea rows={4} placeholder={`${t('common.inputMsg')}${t('skill.form.introduction')}`} />
      </Form.Item>
    </Form>
  );
};

export default SkillForm;
