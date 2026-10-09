'use client';

import { CloseOutlined, FileOutlined, UploadOutlined } from '@ant-design/icons';
import { Button, Form, Input, Typography, Upload, message } from 'antd';

import useApiClient from '@/utils/request';
import { useTranslation } from '@/utils/i18n';
import type { DataReferenceOption } from '../lib/data-references';
import type { JsonSchema } from '../lib/types';
import { FileSampleLinks } from './file-sample-links';
import { ReportContractGuideDrawer } from './report-contract-guide-drawer';
import { SchemaNodeField } from './schema-node-form';
import { WorkflowPermission } from './workflow-permission';

interface Props {
  schema?: JsonSchema;
  value: Record<string, unknown>;
  references: DataReferenceOption[];
  nodeTitle: string;
  readOnly: boolean;
  workflowId?: number | null;
  onChange: (value: Record<string, unknown>) => void;
  onNodeTitleChange: (value: string) => void;
}

interface UploadedTemplate {
  kind?: string;
  name?: string;
  format?: string;
  size?: number;
  placeholders?: string[];
}

interface TemplateSnapshot {
  object_key?: string;
  format?: string;
  size?: number;
  filename_prefix?: string;
  sha256?: string;
}

const field = (schema: JsonSchema | undefined, key: string): JsonSchema => schema?.properties?.[key] || { type: 'object', title: key };
const SAMPLE_SCHEMA: JsonSchema = {
  'x-file-options': {
    accept: ['docx', 'xlsx'],
    maxSizeMiB: 5,
    maxCount: 1,
    sourceModes: ['upload'],
    sampleFiles: [
      { name: 'Word', url: '/workflow-orchestration/templates/health-inspection-example.docx' },
      { name: 'Excel', url: '/workflow-orchestration/templates/health-inspection-example.xlsx' },
    ],
  },
};

function formatBytes(size: number | undefined) {
  if (typeof size !== 'number' || size <= 0) return '';
  if (size < 1024) return `${size} B`;
  if (size < 1024 * 1024) return `${Math.round(size / 1024)} KiB`;
  return `${(size / (1024 * 1024)).toFixed(1)} MiB`;
}

function resolveTemplateEcho(value: Record<string, unknown>) {
  const template = value.template;
  const snapshot = value.template_snapshot;
  if (template && typeof template === 'object' && !Array.isArray(template) && (template as UploadedTemplate).kind === 'uploaded') {
    const uploaded = template as UploadedTemplate;
    const format = String(uploaded.format || '').toLowerCase();
    return {
      name: String(uploaded.name || (format ? `template.${format}` : 'template')),
      format,
      size: typeof uploaded.size === 'number' ? uploaded.size : undefined,
      placeholders: Array.isArray(uploaded.placeholders) ? uploaded.placeholders.map(String) : [],
      source: 'uploaded' as const,
    };
  }
  if (snapshot && typeof snapshot === 'object' && !Array.isArray(snapshot)) {
    const frozen = snapshot as TemplateSnapshot;
    const format = String(frozen.format || '').toLowerCase();
    const prefix = String(frozen.filename_prefix || 'report').trim() || 'report';
    return {
      name: format ? `${prefix}.${format}` : prefix,
      format,
      size: typeof frozen.size === 'number' ? frozen.size : undefined,
      placeholders: [] as string[],
      source: 'snapshot' as const,
    };
  }
  return null;
}

export function DocumentRenderForm({ schema, value, references, nodeTitle, readOnly, workflowId, onChange, onNodeTitleChange }: Props) {
  const { t } = useTranslation();
  const { post } = useApiClient();
  const setField = (key: string, next: unknown) => onChange({ ...value, [key]: next });
  const echo = resolveTemplateEcho(value);

  const clearTemplate = () => {
    const next: Record<string, unknown> = { ...value };
    delete next.template;
    delete next.template_snapshot;
    onChange(next);
  };

  const uploadTemplate = async (file: File) => {
    if (!workflowId) {
      message.error(t('workflowOrchestration.editor.saveBeforeNodeTest', '请先保存流程草稿，再上传模板'));
      return false;
    }
    const extension = file.name.toLowerCase().split('.').pop();
    if (!extension || !['docx', 'xlsx'].includes(extension)) {
      message.error(t('workflowOrchestration.editor.invalidReportTemplateType', '仅支持 .docx 或 .xlsx 模板'));
      return false;
    }
    if (file.size > 5 * 1024 * 1024) {
      message.error(t('workflowOrchestration.editor.reportTemplateTooLarge', '模板文件不能超过 5 MiB'));
      return false;
    }
    const body = new FormData();
    body.append('file', file);
    const uploaded = await post<Record<string, unknown>>(`/workflow_orchestration/api/workflows/${workflowId}/report-template-test-upload/`, body, { headers: { 'Content-Type': 'multipart/form-data' } });
    const next: Record<string, unknown> = { ...value, template: uploaded };
    delete next.template_snapshot;
    onChange(next);
    message.success(t('workflowOrchestration.editor.reportTemplateReady', '模板已上传并完成语法检查'));
    return false;
  };

  return <Form className="flex flex-col gap-5" layout="vertical">
    <Form.Item className="mb-0" label={t('workflowOrchestration.editor.nodeName', '节点名称')} required>
      <Input disabled={readOnly} value={nodeTitle} onChange={(event) => onNodeTitleChange(event.target.value)} />
    </Form.Item>
    <Form.Item
      className="mb-0"
      label={t('workflowOrchestration.editor.documentTemplate', '报告模板')}
      required
      tooltip={t('workflowOrchestration.editor.documentTemplateHint', '保存草稿保留当前文件，发布后固化到该版本')}
    >
      <div className="flex flex-col gap-1.5">
        {echo ? <div className="flex items-start gap-3 rounded-md border border-[var(--color-border-1)] bg-[var(--color-fill-1)] px-3 py-2">
          <FileOutlined className="mt-0.5 text-[var(--color-text-3)]" />
          <div className="min-w-0 flex-1">
            <div className="truncate text-sm font-medium text-[var(--color-text-1)]" title={echo.name}>{echo.name}</div>
            <Typography.Text className="text-xs" type="secondary">
              {[
                echo.format ? echo.format.toUpperCase() : '',
                formatBytes(echo.size),
                echo.source === 'snapshot' ? t('workflowOrchestration.editor.publishedTemplateSnapshot', '已发布固化') : '',
              ].filter(Boolean).join(' · ')}
            </Typography.Text>
            {echo.placeholders.length ? <Typography.Text className="mt-1 block text-xs" type="secondary">
              {t('workflowOrchestration.editor.detectedPlaceholders', '识别到的占位符')}：{echo.placeholders.join('、')}
            </Typography.Text> : null}
          </div>
          {!readOnly ? <WorkflowPermission operation="Edit"><Button
            type="text"
            size="small"
            aria-label={t('workflowOrchestration.editor.removeReportTemplate', '移除报告模板')}
            icon={<CloseOutlined />}
            onClick={clearTemplate}
          /></WorkflowPermission> : null}
        </div> : null}
        {!echo ? <WorkflowPermission operation="Edit"><Upload accept=".docx,.xlsx" maxCount={1} showUploadList={false} disabled={readOnly} beforeUpload={uploadTemplate}>
          <button type="button" className="inline-flex items-center gap-2 rounded-md border border-[var(--color-border-2)] bg-[var(--color-bg)] px-3 py-1.5 text-sm text-[var(--color-text-1)]" disabled={readOnly}>
            <UploadOutlined />
            {t('workflowOrchestration.editor.uploadOfficeTemplate', '上传 Word / Excel 模板')}
          </button>
        </Upload></WorkflowPermission> : null}
        <div className="flex flex-wrap items-center gap-x-3 gap-y-1">
          <FileSampleLinks schema={SAMPLE_SCHEMA} />
          <ReportContractGuideDrawer
            defaultTab="template"
            triggerLabel={t('workflowOrchestration.editor.viewTemplateSyntaxGuide', '模板语法说明')}
          />
        </div>
      </div>
    </Form.Item>
    <Form.Item
      className="mb-0"
      label={t('workflowOrchestration.editor.documentData', '文档数据')}
      required
      tooltip={t('workflowOrchestration.editor.documentDataHint', '拖入上游作业输出，或手写 JSON')}
    >
      <div className="flex flex-col gap-1.5">
        <SchemaNodeField
          schema={{ ...field(schema, 'data'), 'x-widget': 'json', 'x-rows': 12, jsonEditorAllowed: true }}
          value={value.data}
          references={references}
          onChange={(next) => setField('data', next)}
        />
        <div className="self-start">
          <ReportContractGuideDrawer
            defaultTab="structure"
            triggerLabel={t('workflowOrchestration.editor.viewDocumentDataGuide', '数据结构说明')}
          />
        </div>
      </div>
    </Form.Item>
  </Form>;
}
