'use client';

import { Form, InputNumber, Select } from 'antd';
import { useEffect, useMemo, useRef, useState, type ReactNode } from 'react';

import ScriptEditor from '@/components/script-editor';
import { useTranslation } from '@/utils/i18n';
import type { DataReferenceOption } from '../lib/data-references';
import type { JsonSchema, NodeTarget } from '../lib/types';
import { fallbackTargetLabel, targetSourceOf, useResolvedTargets } from './job-selected-targets';
import { ReferenceDropGuard } from './reference-drop-guard';
import { ReportContractGuideDrawer } from './report-contract-guide-drawer';
import { SchemaNodeField } from './schema-node-form';
import { WorkflowNodeTitleField } from './workflow-node-title-field';

type ScriptLang = 'shell' | 'bat' | 'python' | 'powershell';

const SCRIPT_LANGS: ScriptLang[] = ['shell', 'bat', 'python', 'powershell'];

function scriptLang(value: unknown): ScriptLang {
  return SCRIPT_LANGS.includes(value as ScriptLang) ? value as ScriptLang : 'shell';
}

function scriptTemplates(t: (id: string, defaultMessage?: string) => string): Record<ScriptLang, string> {
  return {
    shell: t('job.scriptTemplateShell', '#!/bin/bash\n\n# 任务正常结束\njob_success() {\n    echo "[INFO] Job completed successfully"\n    exit 0\n}\n\n# 任务异常结束\njob_fail() {\n    echo "[ERROR] Job failed"\n    exit 1\n}\n\n# ---------- 在此处编写脚本逻辑 ----------\n\n\n\n# ---------- 结束 ----------\njob_success'),
    bat: t('job.scriptTemplateBat', '@echo off\nREM 在此处编写批处理脚本\n'),
    python: t('job.scriptTemplatePython', '#!/usr/bin/env python3\n# 在此处编写 Python 脚本\n'),
    powershell: t('job.scriptTemplatePowershell', '# 在此处编写 PowerShell 脚本\n'),
  };
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

function ExecutionParamsField({
  value,
  disabled,
  onChange,
}: {
  value: unknown;
  disabled: boolean;
  onChange: (next: string) => void;
}) {
  const { t } = useTranslation();
  const tags = splitParams(value);

  return (
    <ReferenceDropGuard>
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
    </ReferenceDropGuard>
  );
}

export function JobExecuteForm({
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
  const lang = scriptLang(value.script_type);
  const templates = useMemo(() => scriptTemplates(t), [t]);
  const [drafts, setDrafts] = useState<Record<ScriptLang, string>>(() => {
    const current = scriptLang(value.script_type);
    const content = String(value.script_content || '');
    const initial = readOnly ? { shell: '', bat: '', python: '', powershell: '' } : scriptTemplates(t);
    return { ...initial, [current]: content || initial[current] };
  });
  const targetIds = fixedTargetIds(value.targets);
  const { records, mergeRecords } = useResolvedTargets(targetIds);

  useEffect(() => {
    const content = String(value.script_content || '');
    if (!content) return;
    setDrafts((prev) => (prev[lang] === content ? prev : { ...prev, [lang]: content }));
  }, [lang, value.script_content]);

  const seededScript = useRef(Boolean(String(value.script_content || '')));
  useEffect(() => {
    if (readOnly || seededScript.current) return;
    seededScript.current = true;
    onChange({ ...value, script_type: lang, script_content: templates[lang] });
  }, [lang, onChange, readOnly, templates, value]);

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
    description: t('workflowOrchestration.editor.jobTargetsHint', '可从左侧拖入兼容字段或手动填写，也可从节点管理或作业平台选择主机；两个来源不能混选'),
    items: { type: 'string' },
  };
  const targetTooltip = t(
    'workflowOrchestration.editor.jobTargetsHint',
    String(targetSchema.description || '可从左侧拖入兼容字段或手动填写，也可从节点管理或作业平台选择主机；两个来源不能混选'),
  );

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
          onLangChange={(next) => onChange({ ...value, script_type: next, script_content: drafts[next] || templates[next] })}
          onChange={(next) => {
            setDrafts(next);
            onChange({ ...value, script_type: lang, script_content: next[lang] || '' });
          }}
        />
        <div className="self-start">
          <ReportContractGuideDrawer
            mode="structure"
            audience="job"
            triggerLabel={t('workflowOrchestration.editor.viewJobOutputContractGuide', '脚本输出说明')}
          />
        </div>
      </div>
    </Form.Item>
    <Form.Item
      className="mb-0"
      label={t('workflowOrchestration.editor.executionParams', '执行参数')}
      tooltip={t('workflowOrchestration.editor.executionParamsManualHint', '回车添加参数；不支持从左侧拖入上游字段')}
    >
      <ExecutionParamsField
        value={value.execution_params}
        disabled={readOnly}
        onChange={(next) => setField('execution_params', next)}
      />
    </Form.Item>
    <Form.Item className="mb-0" label={t('workflowOrchestration.editor.timeoutSeconds', '超时（秒）')}>
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
