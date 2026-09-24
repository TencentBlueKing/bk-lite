'use client';

import { Form, InputNumber, Select } from 'antd';
import { useEffect, useMemo, useState, type DragEvent, type ReactNode } from 'react';

import ScriptEditor from '@/app/job/components/script-editor';
import { useTranslation } from '@/utils/i18n';
import type { DataReferenceOption } from '../lib/data-references';
import { compatibleDataReferences } from '../lib/data-references';
import type { JsonSchema, NodeTarget } from '../lib/types';
import { fallbackTargetLabel, targetSourceOf, useResolvedTargets } from './job-selected-targets';
import { ReportContractGuideDrawer } from './report-contract-guide-drawer';
import { SchemaNodeField, WORKFLOW_REFERENCE_MIME } from './schema-node-form';

type ScriptLang = 'shell' | 'bat' | 'python' | 'powershell';

const SCRIPT_LANGS: ScriptLang[] = ['shell', 'bat', 'python', 'powershell'];
const PARAMS_SCHEMA: JsonSchema = { type: 'array', items: { type: 'string' } };
const PARAM_ITEM_SCHEMA: JsonSchema = { type: 'string' };

function scriptLang(value: unknown): ScriptLang {
  return SCRIPT_LANGS.includes(value as ScriptLang) ? value as ScriptLang : 'shell';
}

function emptyScripts(): Record<ScriptLang, string> {
  return { shell: '', bat: '', python: '', powershell: '' };
}

function fixedTargetIds(value: unknown): string[] {
  if (!Array.isArray(value)) return [];
  return value.map(String).filter((item) => Boolean(targetSourceOf(item)));
}

function splitParams(raw: unknown): string[] {
  if (Array.isArray(raw)) return raw.map(String).filter((item) => item.trim());
  const text = String(raw ?? '').trim();
  return text ? text.split(/\s+/).filter(Boolean) : [];
}

function joinParams(values: string[]): string {
  return values.map((item) => item.trim()).filter(Boolean).join(' ');
}

function compatibleExecutionParamReferences(references: DataReferenceOption[]) {
  const seen = new Set<string>();
  return [...compatibleDataReferences(references, PARAMS_SCHEMA), ...compatibleDataReferences(references, PARAM_ITEM_SCHEMA)]
    .filter((item) => {
      if (seen.has(item.value)) return false;
      seen.add(item.value);
      return true;
    });
}

function ExecutionParamsField({
  value,
  references,
  disabled,
  onChange,
}: {
  value: unknown;
  references: DataReferenceOption[];
  disabled: boolean;
  onChange: (next: string) => void;
}) {
  const { t } = useTranslation();
  const tags = splitParams(value);
  const compatible = compatibleExecutionParamReferences(references);
  const [isDragOver, setIsDragOver] = useState(false);

  const allowDrop = (event: DragEvent<HTMLDivElement>) => {
    const types = Array.from(event.dataTransfer.types || []);
    const expression = event.dataTransfer.getData(WORKFLOW_REFERENCE_MIME);
    if (types.includes(WORKFLOW_REFERENCE_MIME) || compatible.some((item) => item.value === expression)) {
      event.preventDefault();
      event.dataTransfer.dropEffect = 'copy';
      setIsDragOver(true);
    }
  };

  const acceptDrop = (event: DragEvent<HTMLDivElement>) => {
    const expression = event.dataTransfer.getData(WORKFLOW_REFERENCE_MIME);
    setIsDragOver(false);
    if (!compatible.some((item) => item.value === expression)) return;
    event.preventDefault();
    if (tags.includes(expression)) return;
    onChange(joinParams([...tags, expression]));
  };

  return <div
    data-testid="workflow-reference-dropzone"
    className={`rounded-md outline-none transition focus-within:ring-2 focus-within:ring-[var(--color-primary)]/15 ${isDragOver ? 'ring-2 ring-[var(--color-primary)]/35' : ''}`}
    onDragEnter={allowDrop}
    onDragLeave={() => setIsDragOver(false)}
    onDragOverCapture={allowDrop}
    onDropCapture={acceptDrop}
  >
    <Select
      mode="tags"
      className="w-full"
      disabled={disabled}
      open={false}
      suffixIcon={null}
      tokenSeparators={[' ']}
      value={tags}
      placeholder={t('workflowOrchestration.editor.enterAndPressReturn', '输入后按回车添加')}
      onChange={(next) => onChange(joinParams(next.map(String)))}
    />
  </div>;
}

export function JobExecuteForm({
  schema,
  value,
  references,
  readOnly,
  fieldActions = {},
  targetRecords,
  onChange,
}: {
  schema?: JsonSchema;
  value: Record<string, unknown>;
  references: DataReferenceOption[];
  readOnly: boolean;
  fieldActions?: Record<string, ReactNode>;
  targetRecords?: Record<string, NodeTarget>;
  onChange: (value: Record<string, unknown>) => void;
}) {
  const { t } = useTranslation();
  const lang = scriptLang(value.script_type);
  const [drafts, setDrafts] = useState<Record<ScriptLang, string>>(() => ({
    ...emptyScripts(),
    [scriptLang(value.script_type)]: String(value.script_content || ''),
  }));
  const targetIds = fixedTargetIds(value.targets);
  const { records, mergeRecords } = useResolvedTargets(targetIds);

  useEffect(() => {
    const content = String(value.script_content || '');
    setDrafts((prev) => (prev[lang] === content ? prev : { ...prev, [lang]: content }));
  }, [lang, value.script_content]);

  useEffect(() => {
    if (!targetRecords) return;
    mergeRecords(Object.values(targetRecords));
  }, [mergeRecords, targetRecords]);

  const targetValueLabels = useMemo(() => Object.fromEntries(targetIds.map((id) => {
    const target = targetRecords?.[id] || records[id];
    return [id, target?.name || fallbackTargetLabel(id, t)];
  })), [records, t, targetIds, targetRecords]);

  const setField = (key: string, next: unknown) => onChange({ ...value, [key]: next });
  const targetSchema = schema?.properties?.targets || {
    type: 'array',
    title: t('workflowOrchestration.editor.targetHosts', '目标主机'),
    description: t('workflowOrchestration.editor.jobTargetsHint', '可从左侧拖入兼容字段或手动填写，也可从作业平台选择主机'),
    items: { type: 'string' },
  };
  const targetTooltip = String(targetSchema.description || '') || undefined;

  const targetsEditor = <SchemaNodeField
    schema={targetSchema}
    value={value.targets}
    references={references}
    disabled={readOnly}
    valueLabels={targetValueLabels}
    onChange={(next) => setField('targets', next)}
  />;

  return <Form className="flex flex-col gap-5" layout="vertical">
    <Form.Item
      className="mb-0"
      label={targetSchema.title || t('workflowOrchestration.editor.targetHosts', '目标主机')}
      required
      tooltip={targetTooltip}
    >
      {fieldActions.targets
        ? <div className="flex items-start gap-2"><div className="min-w-0 flex-1">{targetsEditor}</div><div className="shrink-0">{fieldActions.targets}</div></div>
        : targetsEditor}
    </Form.Item>
    <Form.Item
      className="mb-0"
      label={t('workflowOrchestration.editor.scriptContent', '脚本内容')}
      required
    >
      <div className="flex flex-col gap-1.5">
        <ScriptEditor
          readOnly={readOnly}
          activeLang={lang}
          value={drafts}
          onLangChange={(next) => onChange({ ...value, script_type: next, script_content: drafts[next] || '' })}
          onChange={(next) => {
            setDrafts(next);
            onChange({ ...value, script_type: lang, script_content: next[lang] || '' });
          }}
        />
        <div className="self-start">
          <ReportContractGuideDrawer
            defaultTab="structure"
            triggerLabel={t('workflowOrchestration.editor.viewJobOutputContractGuide', '脚本输出说明')}
          />
        </div>
      </div>
    </Form.Item>
    <Form.Item
      className="mb-0"
      label={t('workflowOrchestration.editor.executionParams', '执行参数')}
      tooltip={t('workflowOrchestration.editor.executionParamsHint', '回车添加参数，也可从左侧拖入字段')}
    >
      <ExecutionParamsField
        value={value.execution_params}
        references={references}
        disabled={readOnly}
        onChange={(next) => setField('execution_params', next)}
      />
    </Form.Item>
    <Form.Item className="mb-0" label={t('workflowOrchestration.editor.timeoutSeconds', '超时（秒）')}>
      <InputNumber disabled={readOnly} className="w-full" min={30} max={3600} value={Number(value.timeout_seconds || 600)} onChange={(next) => setField('timeout_seconds', Number(next || 600))} />
    </Form.Item>
  </Form>;
}
