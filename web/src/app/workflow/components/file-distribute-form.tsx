'use client';

import { CloseOutlined, InboxOutlined } from '@ant-design/icons';
import { Form, Input, InputNumber, Radio, Upload, message } from 'antd';
import { useEffect, useMemo, type ReactNode } from 'react';

import useJobApi from '@/app/job/api';
import { useTranslation } from '@/utils/i18n';
import type { DataReferenceOption } from '../lib/data-references';
import type { JsonSchema, NodeTarget } from '../lib/types';
import { fallbackTargetLabel, targetSourceOf, useResolvedTargets } from './job-selected-targets';
import { ReferenceDropGuard } from './reference-drop-guard';
import { SchemaNodeField } from './schema-node-form';
import { WorkflowNodeTitleField } from './workflow-node-title-field';

interface DistributeFile {
  file_key: string;
  name: string;
}

const MAX_FILE_BYTES = 500 * 1024 * 1024;
const MAX_FILE_COUNT = 20;

function fixedTargetIds(value: unknown): string[] {
  if (!Array.isArray(value)) return [];
  return value.map(String).filter((item) => Boolean(targetSourceOf(item)));
}

function normalizeFiles(value: unknown): DistributeFile[] {
  if (!Array.isArray(value)) return [];
  return value.flatMap((item) => {
    if (!item || typeof item !== 'object') return [];
    const record = item as Record<string, unknown>;
    const fileKey = String(record.file_key || '').trim();
    const name = String(record.name || '').trim();
    if (!fileKey || !name) return [];
    return [{ file_key: fileKey, name }];
  });
}

export function FileDistributeForm({
  schema,
  value,
  references,
  nodeTitle,
  readOnly,
  fieldActions = {},
  targetRecords,
  onChange,
  onNodeTitleChange,
}: {
  schema?: JsonSchema;
  value: Record<string, unknown>;
  references: DataReferenceOption[];
  nodeTitle?: string;
  readOnly: boolean;
  fieldActions?: Record<string, ReactNode>;
  targetRecords?: Record<string, NodeTarget>;
  onChange: (value: Record<string, unknown>) => void;
  onNodeTitleChange?: (value: string) => void;
}) {
  const { t } = useTranslation();
  const { uploadDistributionFile } = useJobApi();
  const targetIds = fixedTargetIds(value.targets);
  const { records, mergeRecords } = useResolvedTargets(targetIds);
  const files = useMemo(() => normalizeFiles(value.files), [value.files]);

  useEffect(() => {
    if (!targetRecords) return;
    mergeRecords(Object.values(targetRecords));
  }, [mergeRecords, targetRecords]);

  const setField = (key: string, next: unknown) => onChange({ ...value, [key]: next });
  const targetSchema = schema?.properties?.targets || {
    type: 'array',
    title: t('workflowOrchestration.editor.targetHosts', '目标主机'),
    description: t(
      'workflowOrchestration.editor.fileDistributeTargetsHint',
      '可从左侧拖入表单触发器或上游字段，也可从节点管理或作业平台选择主机；两个来源不能混选',
    ),
    items: { type: 'string' },
  };
  const targetValueLabels = useMemo(() => Object.fromEntries(targetIds.map((id) => {
    const target = targetRecords?.[id] || records[id];
    return [id, target?.name || fallbackTargetLabel(id, t)];
  })), [records, t, targetIds, targetRecords]);

  const targetsEditor = <SchemaNodeField
    schema={targetSchema}
    value={value.targets}
    references={references}
    disabled={readOnly}
    valueLabels={targetValueLabels}
    onChange={(next) => setField('targets', next)}
  />;

  return <Form className="flex flex-col gap-5" layout="vertical">
    {onNodeTitleChange
      ? <WorkflowNodeTitleField value={nodeTitle || ''} disabled={readOnly} onChange={onNodeTitleChange} />
      : null}
    <Form.Item
      className="mb-0"
      label={t('workflowOrchestration.editor.targetHosts', String(targetSchema.title || '目标主机'))}
      required
      tooltip={t(
        'workflowOrchestration.editor.fileDistributeTargetsHint',
        String(targetSchema.description || '可从左侧拖入表单触发器或上游字段，也可从节点管理或作业平台选择主机；两个来源不能混选'),
      )}
    >
      {fieldActions.targets
        ? <div className="flex items-start gap-2"><div className="min-w-0 flex-1">{targetsEditor}</div><div className="shrink-0">{fieldActions.targets}</div></div>
        : targetsEditor}
    </Form.Item>

    <Form.Item
      className="mb-0"
      label={t('workflowOrchestration.editor.distributeFiles', '文件上传')}
      required
      tooltip={t('workflowOrchestration.editor.distributeFilesHint', '支持普通文件或压缩包，单文件不超过 500MB')}
    >
      <ReferenceDropGuard>
        <div className="flex flex-col gap-3">
          {!readOnly ? (
            <Upload.Dragger
              multiple
              showUploadList={false}
              beforeUpload={async (file) => {
                if (files.length >= MAX_FILE_COUNT) {
                  message.error(t('workflowOrchestration.editor.distributeFilesTooMany', '最多上传 {count} 个文件', { count: MAX_FILE_COUNT }));
                  return Upload.LIST_IGNORE;
                }
                if (file.size > MAX_FILE_BYTES) {
                  message.error(t('workflowOrchestration.editor.distributeFileTooLarge', '单文件不能超过 500MB'));
                  return Upload.LIST_IGNORE;
                }
                try {
                  const uploaded = await uploadDistributionFile(file);
                  const fileKey = String(uploaded.file_key || '').trim();
                  const name = String(uploaded.original_name || file.name || '').trim();
                  if (!fileKey || !name) {
                    message.error(t('workflowOrchestration.editor.distributeUploadFailed', '文件上传失败'));
                    return Upload.LIST_IGNORE;
                  }
                  if (files.some((item) => item.file_key === fileKey)) {
                    return Upload.LIST_IGNORE;
                  }
                  setField('files', [...files, { file_key: fileKey, name }]);
                } catch {
                  message.error(t('workflowOrchestration.editor.distributeUploadFailed', '文件上传失败'));
                }
                return Upload.LIST_IGNORE;
              }}
            >
              <p className="ant-upload-drag-icon"><InboxOutlined /></p>
              <p className="ant-upload-text">{t('workflowOrchestration.editor.distributeUploadText', '点击或拖拽文件到此处上传')}</p>
              <p className="ant-upload-hint">{t('workflowOrchestration.editor.distributeUploadHint', '支持普通文件或压缩包，单文件不超过 500MB')}</p>
            </Upload.Dragger>
          ) : null}
          {files.length ? (
            <ul className="m-0 flex list-none flex-col gap-2 p-0">
              {files.map((item) => (
                <li
                  key={item.file_key}
                  className="flex items-center justify-between gap-3 rounded-md border border-[var(--color-border-1)] px-3 py-2"
                >
                  <span className="min-w-0 truncate text-sm text-[var(--color-text-1)]">{item.name}</span>
                  {!readOnly ? (
                    <button
                      type="button"
                      className="inline-flex shrink-0 items-center text-[var(--color-text-3)] hover:text-[var(--color-text-1)]"
                      aria-label={t('common.delete', '删除')}
                      onClick={() => setField('files', files.filter((file) => file.file_key !== item.file_key))}
                    >
                      <CloseOutlined />
                    </button>
                  ) : null}
                </li>
              ))}
            </ul>
          ) : null}
        </div>
      </ReferenceDropGuard>
    </Form.Item>

    <Form.Item
      className="mb-0"
      label={t('workflowOrchestration.editor.targetPath', '目标路径')}
      required
      tooltip={t('workflowOrchestration.editor.targetPathHint', '文件将被分发到目标主机的此路径')}
    >
      <ReferenceDropGuard>
        <Input
          disabled={readOnly}
          value={String(value.target_path || '')}
          placeholder="/etc/nginx/"
          onChange={(event) => setField('target_path', event.target.value)}
        />
      </ReferenceDropGuard>
    </Form.Item>

    <Form.Item className="mb-0" label={t('workflowOrchestration.editor.overwriteStrategy', '覆盖策略')}>
      <ReferenceDropGuard>
        <Radio.Group
          disabled={readOnly}
          value={value.overwrite_strategy === 'skip' ? 'skip' : 'overwrite'}
          onChange={(event) => setField('overwrite_strategy', event.target.value)}
        >
          <Radio value="overwrite">{t('workflowOrchestration.editor.overwriteExisting', '覆盖已存在文件')}</Radio>
          <Radio value="skip">{t('workflowOrchestration.editor.skipExisting', '跳过已存在文件')}</Radio>
        </Radio.Group>
      </ReferenceDropGuard>
    </Form.Item>

    <Form.Item
      className="mb-0"
      label={t('workflowOrchestration.editor.timeoutSeconds', '超时时间（秒）')}
      tooltip={t('workflowOrchestration.editor.fileDistributeTimeoutHint', '文件分发超时时间，超时后将自动终止')}
    >
      <ReferenceDropGuard>
        <InputNumber
          disabled={readOnly}
          className="w-full"
          min={30}
          max={3600}
          value={typeof value.timeout_seconds === 'number' ? value.timeout_seconds : undefined}
          onChange={(next) => setField('timeout_seconds', typeof next === 'number' ? next : undefined)}
        />
      </ReferenceDropGuard>
    </Form.Item>
  </Form>;
}
