'use client';

import { useEffect, useMemo, useState } from 'react';
import { Alert, Button, Collapse, Drawer, Form, Input, InputNumber, Popover, Radio, Select, Space, Switch, Typography, message } from 'antd';
import GroupTreeSelector from '@/components/group-tree-select';
import { useTranslation } from '@/utils/i18n';
import useUnsavedConfirm from '@/hooks/useUnsavedConfirm';
import { useCustomReportingApi } from '@/app/cmdb/api/customReporting';
import { useModelApi } from '@/app/cmdb/api/model';
import { useClassificationApi } from '@/app/cmdb/api/classification';
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
  quick_model_classification_id?: string;
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
  const { getClassificationList } = useClassificationApi();
  const [submitting, setSubmitting] = useState(false);
  const [modelLoading, setModelLoading] = useState(false);
  const [modelOptions, setModelOptions] = useState<ModelOption[]>([]);
  const [classificationOptions, setClassificationOptions] = useState<ModelOption[]>([]);
  const mode = Form.useWatch('mode', form);
  const cleanupStrategy = Form.useWatch('cleanup_strategy', form);
  const selectedModelId = Form.useWatch('model_id', form);
  const selectedModelLabel = useMemo(
    () => modelOptions.find((item) => item.value === selectedModelId)?.label,
    [modelOptions, selectedModelId],
  );

  const isEditingQuickTask = useMemo(
    () => Boolean(task && task.config?.mode === 'quick'),
    [task],
  );

  useEffect(() => {
    if (!open) {
      return;
    }
    // 仅在抽屉打开时拉取一次模型列表。
    // 关键：getModelList 来自 useModelApi，每次渲染都是新的函数引用，绝不能放进依赖数组——
    // 否则 effect 内的 setModelOptions/setModelLoading 触发重渲染 → 新引用 → effect 再次触发，
    // 形成对 /cmdb/api/model 的死循环、页面卡死。依赖仅取 open（与本仓库 common/management 一致）。
    const fetchModelOptions = async () => {
      try {
        setModelLoading(true);
        const [data, classifications] = await Promise.all([
          getModelList(),
          getClassificationList().catch(() => []),
        ]);
        // /cmdb/api/model 返回扁平模型数组（每项含 model_id/model_name），不是分组结构。
        const options = (data || []).map((item: Record<string, any>) => ({
          label: item.model_name || item.model_id,
          value: item.model_id,
        }));
        setModelOptions(options);
        setClassificationOptions(
          (classifications || []).map((item: Record<string, any>) => ({
            label: item.classification_name || item.classification_id,
            value: item.classification_id,
          })),
        );
      } finally {
        setModelLoading(false);
      }
    };
    fetchModelOptions();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open]);

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
      quick_model_classification_id: quickModel?.classification_id,
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
                classification_id: values.quick_model_classification_id,
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
          <Popover
            placement="bottomRight"
            content={
              <div className="max-w-[320px] text-[12px] leading-[20px]">
                <div className="mb-[4px]">
                  <b>{t('CustomReporting.modeStandard')}</b>：
                  {t('CustomReporting.guideStandard')}
                </div>
                <div>
                  <b>{t('CustomReporting.modeQuick')}</b>：
                  {t('CustomReporting.guideQuick')}
                </div>
              </div>
            }
          >
            <Typography.Link>{t('CustomReporting.viewGuide')}</Typography.Link>
          </Popover>
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

        {mode === 'quick' ? (
          <Alert
            type="info"
            showIcon
            className="mb-[16px]"
            message={t('CustomReporting.quickModelHint')}
          />
        ) : null}

        {mode === 'standard' ? (
          <>
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
            {selectedModelId ? (
              <Alert
                type="success"
                showIcon
                className="mb-[16px]"
                message={`${t('CustomReporting.modelSummary')}：${selectedModelLabel || selectedModelId}（${selectedModelId}）`}
                description={t('CustomReporting.modelSummaryHint')}
              />
            ) : null}
          </>
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
            <Form.Item
              label={t('CustomReporting.quickModelClassification')}
              name="quick_model_classification_id"
              rules={[{ required: true, message: t('required') }]}
            >
              <Select
                showSearch
                placeholder={t('common.selectTip')}
                options={classificationOptions}
                optionFilterProp="label"
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

        <Collapse
          ghost
          defaultActiveKey={['advanced']}
          className="mb-[16px]"
          items={[
            {
              key: 'advanced',
              label: t('CustomReporting.advanced'),
              children: (
                <>
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
                </>
              ),
            },
          ]}
        />

        <Form.Item
          label={t('CustomReporting.enabled')}
          name="is_enabled"
          valuePropName="checked"
        >
          <Switch />
        </Form.Item>

        <Alert
          type="info"
          showIcon
          message={t('CustomReporting.credentialHint')}
        />
      </Form>
    </Drawer>
  );
}
