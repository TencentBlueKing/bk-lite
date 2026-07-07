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
  // 管理组织当前值（用于锁定同步进使用组织）
  const manageTeam: number[] = Form.useWatch('team', form) || [];

  useEffect(() => {
    if (!visible) return;
    if (initialValues) {
      // 先 resetFields 清掉上一次编辑的残留（弹窗表单实例跨次打开复用），再回填当前 bot 的值
      form.resetFields();
      form.setFieldsValue({
        ...initialValues,
        // 显式重置使用组织，避免粘连上一次（未保存）的选择；后端未返回该字段时回退到管理组织（不变式 team ⊆ usage_team）
        usage_team: initialValues.usage_team ?? initialValues.team ?? [],
      });
    } else {
      form.resetFields();
      form.setFieldsValue({ bot_type: 3 });
    }
  }, [initialValues, visible]);

  // 管理组织自动并入使用组织（team ⊆ usage_team），并在使用组织里锁定不可删除
  useEffect(() => {
    if (!visible) return;
    const current: number[] = form.getFieldValue('usage_team') || [];
    const merged = Array.from(new Set([...(manageTeam || []), ...current]));
    if (JSON.stringify(merged) !== JSON.stringify(current)) {
      form.setFieldsValue({ usage_team: merged });
    }
  }, [JSON.stringify(manageTeam), visible]);

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
        label={t('studio.form.manageGroup')}
        rules={[{ required: true, message: `${t('common.selectMsg')}${t('studio.form.manageGroup')}` }]}
        initialValue={selectedGroup ? [selectedGroup?.id] : []}
      >
        <GroupTreeSelect placeholder={`${t('common.selectMsg')}${t('studio.form.manageGroup')}`} />
      </Form.Item>
      <Form.Item
        name="usage_team"
        label={t('studio.form.usageGroup')}
        tooltip={t('studio.form.usageGroupTip')}
        rules={[{ required: true, message: `${t('common.selectMsg')}${t('studio.form.usageGroup')}` }]}
        initialValue={selectedGroup ? [selectedGroup?.id] : []}
      >
        <GroupTreeSelect
          placeholder={`${t('common.selectMsg')}${t('studio.form.usageGroup')}`}
          lockedValues={manageTeam}
        />
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
