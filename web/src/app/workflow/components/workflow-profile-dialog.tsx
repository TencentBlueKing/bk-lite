'use client';

import { Button, Form, Input } from 'antd';
import { useEffect } from 'react';

import GroupTreeSelect from '@/components/group-tree-select';
import OperateModal from '@/components/operate-modal';
import { useUserInfoContext } from '@/context/userInfo';
import { useTranslation } from '@/utils/i18n';
import type { WorkflowRecord } from '../lib/types';
import { createCopiedWorkflowName, createDefaultWorkflowName } from '../lib/workflow-draft';
import { WorkflowPermission, type WorkflowOperation, type WorkflowPermissionArea } from './workflow-permission';

export interface WorkflowProfileValue {
  name: string;
  description: string;
  team: number[];
}

type WorkflowProfileMode = 'create' | 'edit' | 'copy';

export function WorkflowProfileDialog({
  open,
  mode,
  workflow,
  marketCopy = false,
  confirmLoading,
  permissionOperation,
  permissionArea = 'workflows',
  onCancel,
  onSubmit,
}: {
  open: boolean;
  mode: WorkflowProfileMode;
  workflow?: WorkflowRecord;
  marketCopy?: boolean;
  confirmLoading: boolean;
  permissionOperation: WorkflowOperation;
  permissionArea?: WorkflowPermissionArea;
  onCancel: () => void;
  onSubmit: (value: WorkflowProfileValue) => void;
}) {
  const { t } = useTranslation();
  const { selectedGroup } = useUserInfoContext();
  const [form] = Form.useForm<WorkflowProfileValue>();
  const organizationLocked = mode === 'edit' && Boolean(workflow?.current_version);
  const submit = () => {
    form.validateFields().then((values) => onSubmit({
      name: values.name.trim(),
      description: (values.description || '').trim(),
      team: values.team,
    })).catch(() => undefined);
  };
  const title = mode === 'create'
    ? t('workflowOrchestration.workflow.create', '新建流程')
    : mode === 'copy'
      ? t('workflowOrchestration.action.copyToWorkflows', '复制到流程')
      : t('workflowOrchestration.workflow.editProfile', '编辑流程');

  useEffect(() => {
    if (!open) return;
    const currentTeam = selectedGroup?.id ? [Number(selectedGroup.id)] : [];
    const defaultName = createDefaultWorkflowName(new Date(), t('workflowOrchestration.workflow.defaultNamePrefix', '流程'));
    if (mode === 'create') {
      form.setFieldsValue({ name: defaultName, description: '', team: currentTeam });
      return;
    }
    if (!workflow) return;
    form.setFieldsValue({
      name: mode === 'copy' ? createCopiedWorkflowName(workflow.name) : workflow.name,
      description: workflow.description || '',
      team: mode === 'copy' ? currentTeam : (workflow.team?.length ? workflow.team : currentTeam),
    });
  }, [form, mode, open, selectedGroup?.id, t, workflow]);

  return (
    <OperateModal
      title={title}
      open={open}
      confirmLoading={confirmLoading}
      okText={mode === 'copy'
        ? t('workflowOrchestration.action.confirmDuplicate', '确认复制')
        : t('common.confirm', '确定')}
      cancelText={t('common.cancel', '取消')}
      styles={{ footer: { marginTop: 20 } }}
      destroyOnHidden
      onCancel={onCancel}
      footer={(
        <div className="flex justify-end gap-2">
          <Button onClick={onCancel}>{t('common.cancel', '取消')}</Button>
          <WorkflowPermission operation={permissionOperation} area={permissionArea} instancePermissions={mode === 'edit' ? workflow?.permission : undefined}>
            <Button type="primary" loading={confirmLoading} onClick={submit}>{mode === 'copy' ? t('workflowOrchestration.action.confirmDuplicate', '确认复制') : t('common.confirm', '确定')}</Button>
          </WorkflowPermission>
        </div>
      )}
    >
      {marketCopy ? <p className="mb-3 text-sm text-[var(--color-text-3)]">{t('workflowOrchestration.workflow.marketDuplicateHint', '复制后出现在「流程」里，状态是纯草稿，不会发布，也不会改动这条内置流程。')}</p> : null}
      <Form form={form} layout="vertical" requiredMark>
        <Form.Item
          name="name"
          label={t('workflowOrchestration.workflow.name', '流程名称')}
          rules={[{ required: true, whitespace: true, message: t('workflowOrchestration.workflow.nameRequired', '请填写流程名称') }]}
        >
          <Input maxLength={120} autoFocus />
        </Form.Item>
        <Form.Item
          name="team"
          label={t('workflowOrchestration.workflow.organization', '组织')}
          rules={[{ required: true, type: 'array', min: 1, message: t('workflowOrchestration.workflow.organizationRequired', '请选择组织') }]}
        >
          <GroupTreeSelect multiple disabled={organizationLocked} placeholder={t('workflowOrchestration.workflow.organizationRequired', '请选择组织')} />
        </Form.Item>
        <Form.Item name="description" label={t('workflowOrchestration.workflow.description', '描述')}>
          <Input.TextArea rows={3} maxLength={500} />
        </Form.Item>
      </Form>
    </OperateModal>
  );
}
