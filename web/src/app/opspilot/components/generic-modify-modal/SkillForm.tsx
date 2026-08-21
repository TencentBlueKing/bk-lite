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
  // 管理组织当前值（用于锁定同步进使用组织）
  const manageTeam: number[] = Form.useWatch('team', form) || [];

  useEffect(() => {
    if (!visible) return;
    if (initialValues) {
      form.resetFields();
      form.setFieldsValue({
        ...initialValues,
        skill_type: initialValues.skill_type ?? DEFAULT_SKILL_TYPE,
        usage_team: (Array.isArray(initialValues.usage_team) && initialValues.usage_team.length > 0)
          ? initialValues.usage_team
          : (initialValues.team ?? []),
      });
    } else {
      form.resetFields();
      form.setFieldsValue({ skill_type: DEFAULT_SKILL_TYPE });
    }
  }, [initialValues, visible]);

  // 管理组织自动并入使用组织（team ⊆ usage_team），并在使用组织里锁定不可删除
  useEffect(() => {
    if (!visible) return;
    const current = (form.getFieldValue('usage_team') || []).map(Number).filter((n: number) => !Number.isNaN(n));
    const manage = (manageTeam || []).map(Number).filter((n: number) => !Number.isNaN(n));
    const merged = Array.from(new Set([...manage, ...current]));
    if (JSON.stringify(merged) !== JSON.stringify(current)) {
      form.setFieldsValue({ usage_team: merged });
    }
  }, [JSON.stringify(manageTeam), visible]);

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
        label={t('skill.form.manageGroup')}
        rules={[{ required: true, message: `${t('common.selectMsg')}${t('skill.form.manageGroup')}` }]}
        initialValue={selectedGroup ? [selectedGroup?.id] : []}
      >
        <GroupTreeSelect placeholder={`${t('common.selectMsg')}${t('skill.form.manageGroup')}`} />
      </Form.Item>
      <Form.Item
        name="usage_team"
        label={t('skill.form.usageGroup')}
        tooltip={t('skill.form.usageGroupTip')}
        rules={[{ required: true, message: `${t('common.selectMsg')}${t('skill.form.usageGroup')}` }]}
        initialValue={selectedGroup ? [selectedGroup?.id] : []}
      >
        <GroupTreeSelect
          placeholder={`${t('common.selectMsg')}${t('skill.form.usageGroup')}`}
          lockedValues={manageTeam}
        />
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
