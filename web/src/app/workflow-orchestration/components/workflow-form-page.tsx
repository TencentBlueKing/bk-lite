'use client';

import { ArrowRightOutlined, ExperimentOutlined, SendOutlined } from '@ant-design/icons';
import { Alert, App, Button, Card, Empty, Result, Skeleton, Tag } from 'antd';
import { useCallback, useMemo, useState } from 'react';
import { useRouter } from 'next/navigation';

import useApiClient from '@/utils/request';
import { useTranslation } from '@/utils/i18n';
import { workflowTriggerNodes, type WorkflowCanvasMetadata } from '../lib/canvas-dsl';
import type { ExecutionRecord, WorkflowRecord, WorkflowTriggerRecord } from '../lib/types';
import { useAutoRequest, useRequestCoordinator } from '../lib/use-request-coordinator';
import { missingRequiredFields, WorkflowSchemaForm } from './workflow-schema-form';
import { WorkflowPermission } from './workflow-permission';

const API = '/workflow_orchestration/api';

interface FormSource {
  name: string;
  description: string;
  schema: WorkflowTriggerRecord['input_schema'];
  enabled: boolean;
}

export function WorkflowFormPage({
  mode,
  workflowId,
  triggerId,
  nodeKey,
}: {
  mode: 'test' | 'production';
  workflowId?: number;
  triggerId?: string;
  nodeKey?: string;
}) {
  const router = useRouter();
  const { get, post } = useApiClient();
  const { message } = App.useApp();
  const { t } = useTranslation();
  const [source, setSource] = useState<FormSource>();
  const [inputs, setInputs] = useState<Record<string, unknown>>({});
  const [execution, setExecution] = useState<ExecutionRecord>();
  const [loading, setLoading] = useState(true);
  const [submitting, setSubmitting] = useState(false);
  const coordinator = useRequestCoordinator(setLoading);

  const load = useCallback(async () => {
    const ticket = coordinator.begin({ visible: true });
    if (!ticket) return;
    try {
      if (mode === 'test' && workflowId && nodeKey) {
        const workflow = await get<WorkflowRecord>(`${API}/workflows/${workflowId}/`, { signal: ticket.signal });
        if (!coordinator.shouldApply(ticket)) return;
        const trigger = workflowTriggerNodes(workflow.canvas_metadata as WorkflowCanvasMetadata).find((item) => item.id === nodeKey && item.trigger_type === 'FORM');
        setSource(trigger ? { name: trigger.name, description: workflow.description || '', schema: trigger.input_schema, enabled: true } : undefined);
        return;
      }
      if (mode === 'production' && triggerId) {
        const trigger = await get<WorkflowTriggerRecord>(`${API}/triggers/${encodeURIComponent(triggerId)}/`, { signal: ticket.signal });
        if (!coordinator.shouldApply(ticket)) return;
        setSource(trigger.trigger_type === 'FORM' ? { name: trigger.name, description: trigger.workflow_name || '', schema: trigger.input_schema, enabled: trigger.enabled } : undefined);
      }
    } catch {
      if (coordinator.shouldApply(ticket)) setSource(undefined);
    } finally {
      coordinator.finish(ticket);
    }
  }, [coordinator, get, mode, nodeKey, triggerId, workflowId]);

  useAutoRequest(`workflow-form:${mode}:${workflowId || ''}:${triggerId || ''}:${nodeKey || ''}`, load);

  const title = source?.name || (mode === 'test' ? t('workflowOrchestration.form.testForm', '测试表单') : t('workflowOrchestration.form.workflowForm', '流程表单'));
  const submit = async () => {
    if (!source) return;
    const missing = missingRequiredFields(source.schema, inputs);
    if (missing.length) {
      message.warning(t('workflowOrchestration.form.completeRequired', '请完成必填字段：{fields}', { fields: missing.map((key) => source.schema.properties?.[key]?.title || key).join('、') }));
      return;
    }
    setSubmitting(true);
    try {
      const created = mode === 'test'
        ? await post<ExecutionRecord>(`${API}/workflows/${workflowId}/debug/`, { inputs, trigger_id: nodeKey })
        : await post<ExecutionRecord>(`${API}/triggers/${encodeURIComponent(triggerId || '')}/invoke/`, { inputs, idempotency_key: crypto.randomUUID() });
      setExecution(created);
    } finally {
      setSubmitting(false);
    }
  };

  const empty = useMemo(() => !source || Object.keys(source.schema.properties || {}).length === 0, [source]);

  if (loading) return <div className="mx-auto w-full max-w-2xl p-6"><Skeleton active paragraph={{ rows: 8 }} /></div>;
  if (!source) return <div className="grid h-full min-h-96 place-items-center"><Empty description={t('workflowOrchestration.form.notFound', '表单入口不存在或已失效')} /></div>;
  if (execution) return (
    <div className="grid h-full min-h-96 place-items-center p-6">
      <Result
        status="success"
        title={mode === 'test' ? t('workflowOrchestration.form.debugStarted', '调试执行已启动') : t('workflowOrchestration.form.submitted', '流程已提交')}
        subTitle={t('workflowOrchestration.form.executionId', '执行 ID：{id}', { id: execution.id })}
        extra={<WorkflowPermission operation="View" area="executions" instancePermissions={execution.permission}><Button type="primary" icon={<ArrowRightOutlined />} onClick={() => router.push(`/workflow-orchestration/executions/${execution.id}`)}>{t('workflowOrchestration.form.viewExecution', '查看执行详情')}</Button></WorkflowPermission>}
      />
    </div>
  );

  return (
    <main className="h-full min-h-0 overflow-y-auto bg-[var(--color-bg-1)] px-4 py-8 sm:px-6">
      <Card className="mx-auto w-full max-w-2xl" styles={{ body: { padding: 24 } }}>
        <div className="mb-6 border-b border-[var(--color-border-1)] pb-5">
          <div className="flex items-center gap-3">
            <span className="grid h-10 w-10 place-items-center rounded-lg bg-[var(--color-fill-2)] text-xl text-[var(--color-primary)]">
              {mode === 'test' ? <ExperimentOutlined /> : <SendOutlined />}
            </span>
            <div className="min-w-0">
              <div className="flex items-center gap-2">
                <h1 className="m-0 truncate text-xl font-semibold text-[var(--color-text-1)]">{title}</h1>
                {mode === 'test' ? <Tag color="processing">{t('workflowOrchestration.form.test', '测试')}</Tag> : <Tag color="success">{t('workflowOrchestration.form.production', '生产')}</Tag>}
              </div>
              {source.description ? <p className="mb-0 mt-1 text-sm text-[var(--color-text-3)]">{source.description}</p> : null}
            </div>
          </div>
        </div>
        {!source.enabled ? <Alert className="mb-5" type="warning" showIcon message={t('workflowOrchestration.form.workflowDisabled', '当前流程已停用，暂时不能提交')} /> : null}
        {empty ? <Empty className="py-8" description={t('workflowOrchestration.form.noFields', '该表单尚未配置字段')} /> : <WorkflowSchemaForm schema={source.schema} value={inputs} onChange={setInputs} disabled={!source.enabled || submitting} />}
        <div className="mt-6 flex justify-end border-t border-[var(--color-border-1)] pt-5">
          <WorkflowPermission operation="Execute"><Button type="primary" loading={submitting} disabled={!source.enabled || empty} icon={<SendOutlined />} onClick={() => void submit()}>{t('common.submit', '提交')}</Button></WorkflowPermission>
        </div>
      </Card>
    </main>
  );
}
