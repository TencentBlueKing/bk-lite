'use client';

import { useEffect, useMemo, useState } from 'react';
import { Button, Drawer, Form, Input, InputNumber, Radio, Select, Space, Switch, message } from 'antd';
import GroupTreeSelector from '@/components/group-tree-select';
import { useTranslation } from '@/utils/i18n';
import useUnsavedConfirm from '@/hooks/useUnsavedConfirm';
import { useCustomReportingApi } from '@/app/cmdb/api/customReporting';
import { useModelApi } from '@/app/cmdb/api/model';
import type {
  CustomReportingCleanupStrategy,
  CustomReportingCreateTaskPayload,
  CustomReportingMode,
  CustomReportingTask,
  CustomReportingUpdateTaskPayload,
} from '@/app/cmdb/types/customReporting';

interface ModelOption {
  label: string;
  value: string;
}

interface TaskWizardProps {
  open: boolean;
  task?: CustomReportingTask | null;
  onClose: () => void;
  onSaved: () => void;
}

interface TaskWizardFormValues {
  name: string;
  team: number[];
  mode: CustomReportingMode;
  model_id?: string;
  quick_model_id?: string;
  quick_model_name?: string;
  identity_keys: string[];
  cleanup_strategy?: CustomReportingCleanupStrategy;
  expire_days?: number | null;
  snapshot_delete_ratio_threshold?: number | null;
  is_enabled: boolean;
}

const normalizeIdentityKeys = (values: string[] | undefined) =>
  (values || [])
    .map((item) => String(item || '').trim())
    .filter(Boolean)
    .filter((item, index, arr) => arr.indexOf(item) === index);

export default function TaskWizard({
  open,
  task,
  onClose,
  onSaved,
}: TaskWizardProps) {
  const { t } = useTranslation();
  const guardClose = useUnsavedConfirm();
  const [form] = Form.useForm<TaskWizardFormValues>();
  const handleClose = () => guardClose(form.isFieldsTouched(), onClose);
  const { createTask, updateTask } = useCustomReportingApi();
  const { getModelList } = useModelApi();
  const [submitting, setSubmitting] = useState(false);
  const [modelLoading, setModelLoading] = useState(false);
  const [modelOptions, setModelOptions] = useState<ModelOption[]>([]);
  const mode = Form.useWatch('mode', form);
  const cleanupStrategy = Form.useWatch('cleanup_strategy', form);

  const isEditingQuickTask = useMemo(
    () => Boolean(task && task.config?.mode === 'quick'),
    [task],
  );

  useEffect(() => {
    if (!open) {
      return;
    }
    const fetchModelOptions = async () => {
      try {
        setModelLoading(true);
        const data = await getModelList();
        const options = (data || []).flatMap((group: Record<string, any>) =>
          (group.list || []).map((item: Record<string, any>) => ({
            label: item.model_name || item.model_id,
            value: item.model_id,
          })),
        );
        setModelOptions(options);
      } finally {
        setModelLoading(false);
      }
    };
    fetchModelOptions();
  }, [getModelList, open]);

  useEffect(() => {
    if (!open) {
      form.resetFields();
      return;
    }

    if (!task) {
      form.setFieldsValue({
        name: '',
        team: [],
        mode: 'standard',
        identity_keys: ['inst_name'],
        cleanup_strategy: 'none',
        is_enabled: true,
      });
      return;
    }

    const quickModel = task.config?.quick_model;
    form.setFieldsValue({
      name: task.name,
      team: task.team || [],
      mode: task.config?.mode || 'standard',
      model_id: task.config?.model_id,
      quick_model_id: quickModel?.model_id,
      quick_model_name: quickModel?.model_name,
      identity_keys: quickModel?.identity_keys || task.config?.identity_keys || ['inst_name'],
      cleanup_strategy: (task.config?.cleanup_strategy as CustomReportingCleanupStrategy) || 'none',
      expire_days: task.config?.expire_days ?? undefined,
      snapshot_delete_ratio_threshold: task.config?.snapshot_delete_ratio_threshold ?? undefined,
      is_enabled: task.is_enabled,
    });
  }, [form, open, task]);

  const handleSubmit = async () => {
    try {
      const values = await form.validateFields();
      const identityKeys = normalizeIdentityKeys(values.identity_keys);
      const config = {
        mode: values.mode,
        identity_keys: identityKeys,
        cleanup_strategy: values.cleanup_strategy,
        expire_days:
          values.cleanup_strategy === 'expire' ? values.expire_days ?? null : null,
        snapshot_delete_ratio_threshold:
          values.cleanup_strategy === 'snapshot'
            ? values.snapshot_delete_ratio_threshold ?? null
            : null,
        ...(values.mode === 'standard' ? { model_id: values.model_id } : {}),
      };

      const basePayload = {
        name: values.name.trim(),
        team: values.team?.map((item) => Number(item)).filter((item) => !Number.isNaN(item)),
        config,
        is_enabled: values.is_enabled,
      };

      setSubmitting(true);
      if (task) {
        const payload: CustomReportingUpdateTaskPayload = basePayload;
        await updateTask(task.id, payload);
        message.success(t('successfullyModified'));
      } else {
        const payload: CustomReportingCreateTaskPayload = {
          ...basePayload,
          quick_model:
            values.mode === 'quick'
              ? {
                model_id: String(values.quick_model_id || '').trim(),
                model_name: String(values.quick_model_name || '').trim(),
                identity_keys: identityKeys,
              }
              : undefined,
        };
        await createTask(payload);
        message.success(t('successfullyAdded'));
      }
      onSaved();
      onClose();
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <Drawer
      title={task ? t('CustomReporting.editTask') : t('CustomReporting.createTask')}
      open={open}
      onClose={handleClose}
      maskClosable={false}
      keyboard={false}
      width={640}
      destroyOnClose
      extra={
        <Space>
          <Button onClick={handleClose}>{t('common.cancel')}</Button>
          <Button type="primary" loading={submitting} onClick={handleSubmit}>
            {t('common.confirm')}
          </Button>
        </Space>
      }
    >
      <Form form={form} layout="vertical">
        <Form.Item
          label={t('CustomReporting.taskName')}
          name="name"
          rules={[{ required: true, message: t('required') }]}
        >
          <Input placeholder={t('common.inputTip')} />
        </Form.Item>

        <Form.Item
          label={t('CustomReporting.teamScope')}
          name="team"
          rules={[{ required: true, message: t('required') }]}
        >
          <GroupTreeSelector placeholder={t('common.selectTip')} />
        </Form.Item>

        <Form.Item
          label={t('CustomReporting.mode')}
          name="mode"
          rules={[{ required: true, message: t('required') }]}
        >
          <Radio.Group>
            <Radio.Button value="standard">
              {t('CustomReporting.modeStandard')}
            </Radio.Button>
            <Radio.Button value="quick">
              {t('CustomReporting.modeQuick')}
            </Radio.Button>
          </Radio.Group>
        </Form.Item>

        {mode === 'standard' ? (
          <Form.Item
            label={t('CustomReporting.targetModel')}
            name="model_id"
            rules={[{ required: true, message: t('required') }]}
          >
            <Select
              showSearch
              loading={modelLoading}
              placeholder={t('common.selectTip')}
              options={modelOptions}
              optionFilterProp="label"
            />
          </Form.Item>
        ) : (
          <>
            <Form.Item
              label={t('CustomReporting.quickModelId')}
              name="quick_model_id"
              rules={[{ required: true, message: t('required') }]}
            >
              <Input
                placeholder={t('common.inputTip')}
                disabled={isEditingQuickTask}
              />
            </Form.Item>
            <Form.Item
              label={t('CustomReporting.quickModelName')}
              name="quick_model_name"
              rules={[{ required: true, message: t('required') }]}
            >
              <Input
                placeholder={t('common.inputTip')}
                disabled={isEditingQuickTask}
              />
            </Form.Item>
          </>
        )}

        <Form.Item
          label={t('CustomReporting.identityKeys')}
          name="identity_keys"
          rules={[{ required: true, message: t('required') }]}
          extra={t('CustomReporting.identityKeysHelp')}
        >
          <Select
            mode="tags"
            tokenSeparators={[',', ' ']}
            placeholder={t('CustomReporting.identityKeysPlaceholder')}
          />
        </Form.Item>

        <Form.Item
          label={t('CustomReporting.cleanupStrategy')}
          name="cleanup_strategy"
        >
          <Radio.Group>
            <Radio.Button value="none">
              {t('CustomReporting.cleanupNone')}
            </Radio.Button>
            <Radio.Button value="expire">
              {t('CustomReporting.cleanupExpire')}
            </Radio.Button>
            <Radio.Button value="snapshot">
              {t('CustomReporting.cleanupSnapshot')}
            </Radio.Button>
          </Radio.Group>
        </Form.Item>

        {cleanupStrategy === 'expire' ? (
          <Form.Item
            label={t('CustomReporting.expireDays')}
            name="expire_days"
            rules={[{ required: true, message: t('required') }]}
          >
            <InputNumber min={1} className="w-full" />
          </Form.Item>
        ) : null}

        {cleanupStrategy === 'snapshot' ? (
          <Form.Item
            label={t('CustomReporting.snapshotThreshold')}
            name="snapshot_delete_ratio_threshold"
            rules={[{ required: true, message: t('required') }]}
          >
            <InputNumber min={0} max={100} className="w-full" />
          </Form.Item>
        ) : null}

        <Form.Item
          label={t('CustomReporting.enabled')}
          name="is_enabled"
          valuePropName="checked"
        >
          <Switch />
        </Form.Item>
      </Form>
    </Drawer>
  );
}
