'use client';

import { UploadOutlined } from '@ant-design/icons';
import { App, Button, Form, Upload } from 'antd';
import { useCallback, useMemo, useState } from 'react';

import OperateModal from '@/components/operate-modal';
import { useTranslation } from '@/utils/i18n';
import useApiClient from '@/utils/request';

import type { JsonSchema, NodeTarget, WorkflowTargetField } from '../lib/types';
import { FileSampleLinks } from './file-sample-links';
import { RuntimeTargetSelector, WORKFLOW_NESTED_SELECTOR_Z_INDEX } from './workflow-launch-dialog';
import { WorkflowPermission } from './workflow-permission';
import { WorkflowSchemaForm } from './workflow-schema-form';

const API = '/workflow_orchestration/api';

interface UploadedRuntimeFile {
  kind: 'uploaded';
  name: string;
  format: 'docx' | 'xlsx';
  size: number;
  token: string;
}

export function defaultTriggerRuntimeInputs(schema: JsonSchema): Record<string, unknown> {
  return Object.fromEntries(Object.entries(schema.properties || {}).flatMap(([key, field]) => {
    if ('default' in field) return [[key, field.default]];
    if (field.type === 'boolean') return [[key, false]];
    if (field.type === 'array') return [[key, []]];
    return [];
  }));
}

export function triggerTargetFields(schema: JsonSchema): WorkflowTargetField[] {
  return Object.entries(schema.properties || {}).flatMap(([key, field]) => {
    const binding = field['x-target-binding'];
    if (!binding || binding.mode !== 'runtime') return [];
    return [{
      key,
      name: field.title || key,
      required: Boolean(schema.required?.includes(key)),
      binding_mode: 'runtime' as const,
      allowed_sources: binding.allowedSources,
      allowed_operating_systems: binding.allowedOperatingSystems,
      min_count: schema.required?.includes(key) ? 1 : 0,
      max_count: binding.maxCount,
    }];
  });
}

function TestFileUpload({ workflowId, fieldKey, schema, value, disabled, onChange }: {
  workflowId: number;
  fieldKey: string;
  schema: JsonSchema;
  value: unknown;
  disabled: boolean;
  onChange: (value: UploadedRuntimeFile) => void;
}) {
  const { post } = useApiClient();
  const { message } = App.useApp();
  const { t } = useTranslation();
  const [uploading, setUploading] = useState(false);
  const current = value && typeof value === 'object' && !Array.isArray(value) ? value as Partial<UploadedRuntimeFile> : {};
  const options = schema['x-file-options'];
  const formats = options?.accept?.length ? options.accept : ['docx', 'xlsx'];
  const maxSizeMiB = options?.maxSizeMiB || 5;

  return <div className="space-y-3 rounded-lg border border-[var(--color-border-1)] p-4">
    <Upload
      accept={formats.map((item) => `.${item}`).join(',')}
      disabled={disabled || uploading}
      maxCount={options?.maxCount || 1}
      showUploadList={false}
      beforeUpload={async (file) => {
        if (file.size > maxSizeMiB * 1024 * 1024) {
          message.error(t('workflowOrchestration.launch.templateTooLarge', '文件不能超过 {size} MiB', { size: maxSizeMiB }));
          return Upload.LIST_IGNORE;
        }
        setUploading(true);
        try {
          const body = new FormData();
          body.append('field_key', fieldKey);
          body.append('file', file);
          const uploaded = await post<UploadedRuntimeFile>(`${API}/workflows/${workflowId}/report-template-test-upload/`, body, { headers: { 'Content-Type': 'multipart/form-data' } });
          onChange(uploaded);
          message.success(t('workflowOrchestration.launch.templateUploaded', '报告模板已上传'));
        } finally {
          setUploading(false);
        }
        return Upload.LIST_IGNORE;
      }}
    >
      <Button disabled={disabled} loading={uploading} icon={<UploadOutlined />}>
        {current.name ? t('workflowOrchestration.launch.replaceTemplate', '更换模板') : t('workflowOrchestration.launch.chooseTemplate', '选择 Word / Excel 模板')}
      </Button>
    </Upload>
    {current.name ? <div className="text-xs text-[var(--color-text-3)]">{current.name} · {Math.ceil(Number(current.size || 0) / 1024)} KiB</div> : null}
    <FileSampleLinks schema={schema} />
    <div className="text-xs leading-5 text-[var(--color-text-3)]">
      {t('workflowOrchestration.launch.templateHint', '支持 {formats}，单文件不超过 {size} MiB。', { formats: formats.map((item) => `.${item}`).join(' / '), size: maxSizeMiB })}
    </div>
  </div>;
}

export function WorkflowTriggerRuntimeForm({ workflowId, schema, value, disabled = false, onChange }: {
  workflowId: number;
  schema: JsonSchema;
  value: Record<string, unknown>;
  disabled?: boolean;
  onChange: (value: Record<string, unknown>) => void;
}) {
  const { t } = useTranslation();
  const targetFields = useMemo(() => triggerTargetFields(schema), [schema]);
  const targetFieldMap = useMemo(() => Object.fromEntries(targetFields.map((item) => [item.key, item])), [targetFields]);
  const [targetDialogField, setTargetDialogField] = useState<WorkflowTargetField>();
  const [targetDraft, setTargetDraft] = useState<string[]>([]);
  const [targetDraftBlocked, setTargetDraftBlocked] = useState(false);
  const [targetRecords, setTargetRecords] = useState<Record<string, NodeTarget>>({});
  const discoverTargets = useCallback((records: NodeTarget[]) => {
    setTargetRecords((current) => ({ ...current, ...Object.fromEntries(records.map((item) => [item.id, item])) }));
  }, []);
  const setField = (key: string, next: unknown) => onChange({ ...value, [key]: next });
  const openTargetDialog = (field: WorkflowTargetField) => {
    setTargetDialogField(field);
    setTargetDraft(Array.isArray(value[field.key]) ? value[field.key] as string[] : []);
    setTargetDraftBlocked(false);
  };
  const confirmTargetDialog = () => {
    if (!targetDialogField) return;
    setField(targetDialogField.key, targetDraft);
    setTargetDialogField(undefined);
  };

  return <>
    <div className="flex flex-col gap-4">
      {Object.entries(schema.properties || {}).map(([key, field]) => {
        const targetField = targetFieldMap[key];
        const required = schema.required?.includes(key);
        if (targetField) {
          const selectedCount = Array.isArray(value[key]) ? value[key].length : 0;
          const jobOnly = targetField.allowed_sources.length === 1 && targetField.allowed_sources[0] === 'job_mgmt';
          return <Form.Item className="mb-0" key={key} label={field.title || key} required={required} tooltip={field.description || undefined}>
            <WorkflowPermission operation="Execute" className="block w-full">
              <button
                type="button"
                disabled={disabled}
                className="flex w-full items-center justify-between gap-4 rounded-lg border border-[var(--color-border-1)] px-4 py-3 text-left transition-colors hover:border-[var(--color-primary)] focus-visible:outline-2 focus-visible:outline-[var(--color-primary)] disabled:cursor-not-allowed disabled:opacity-60"
                onClick={() => openTargetDialog(targetField)}
              >
                <span>
                  <span className="block text-sm font-medium text-[var(--color-text-1)]">{selectedCount ? t('workflowOrchestration.launch.hostsSelected', '已选择 {count} 台主机', { count: selectedCount }) : t('workflowOrchestration.launch.selectHosts', '请选择目标主机')}</span>
                  <span className="mt-1 block text-xs text-[var(--color-text-3)]">{t('workflowOrchestration.launch.selectorHint', '点击打开主机选择器，确认后回填本执行表单')}</span>
                </span>
                <span className="shrink-0 text-sm text-[var(--color-primary)]">{jobOnly ? t('workflowOrchestration.editor.selectJobHosts', '选择作业平台主机') : t('workflowOrchestration.launch.selectTarget', '选择主机')}</span>
              </button>
            </WorkflowPermission>
          </Form.Item>;
        }
        if (field['x-widget'] === 'file-upload') {
          return <Form.Item className="mb-0" key={key} label={field.title || key} required={required} tooltip={field.description || undefined}>
            <TestFileUpload workflowId={workflowId} fieldKey={key} schema={field} value={value[key]} disabled={disabled} onChange={(next) => setField(key, next)} />
          </Form.Item>;
        }
        return <WorkflowSchemaForm
          key={key}
          schema={{ type: 'object', properties: { [key]: field }, required: required ? [key] : [], additionalProperties: false }}
          value={{ [key]: value[key] }}
          disabled={disabled}
          onChange={(next) => setField(key, next[key])}
        />;
      })}
    </div>
    <OperateModal
      width={1040}
      title={targetDialogField?.allowed_sources.length === 1 && targetDialogField.allowed_sources[0] === 'job_mgmt'
        ? t('workflowOrchestration.editor.selectJobHostsTitle', '选择作业平台主机')
        : targetDialogField ? t('workflowOrchestration.launch.selectTargetTitle', '选择主机 · {name}', { name: targetDialogField.name }) : t('workflowOrchestration.launch.selectTarget', '选择主机')}
      open={Boolean(targetDialogField)}
      destroyOnHidden
      zIndex={WORKFLOW_NESTED_SELECTOR_Z_INDEX}
      footer={<div className="flex justify-end gap-2"><Button onClick={() => setTargetDialogField(undefined)}>{t('common.cancel', '取消')}</Button><Button type="primary" disabled={!targetDialogField || targetDraft.length < targetDialogField.min_count || targetDraft.length > targetDialogField.max_count || targetDraftBlocked} onClick={confirmTargetDialog}>{t('workflowOrchestration.launch.confirmSelection', '确认选择')}</Button></div>}
      styles={{ body: { maxHeight: 'calc(100vh - 220px)', overflowY: 'auto', paddingBlock: 24 }, footer: { marginTop: 8 } }}
      onCancel={() => setTargetDialogField(undefined)}
    >
      {targetDialogField ? <RuntimeTargetSelector field={targetDialogField} value={targetDraft} onChange={setTargetDraft} onBlockingChange={setTargetDraftBlocked} recordCache={targetRecords} onRecordsDiscovered={discoverTargets} /> : null}
    </OperateModal>
  </>;
}
