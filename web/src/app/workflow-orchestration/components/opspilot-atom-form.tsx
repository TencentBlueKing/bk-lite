'use client';

import { DeleteOutlined, InboxOutlined, MinusOutlined, PlusOutlined } from '@ant-design/icons';
import { Alert, App, Button, Collapse, Form, Input, InputNumber, Radio, Select, Upload } from 'antd';
import type { UploadFile } from 'antd';
import { useEffect, useMemo, useState } from 'react';

import useApiClient from '@/utils/request';
import { useTranslation } from '@/utils/i18n';

import type { DataReferenceOption } from '../lib/data-references';
import type { JsonSchema } from '../lib/types';
import { WorkflowPermission } from './workflow-permission';
import { SchemaNodeField } from './schema-node-form';

const API = '/workflow_orchestration/api';
export const OPSPILOT_ATOM_KEYS = new Set([
  'bklite_agent',
  'bklite_intent_classification',
  'bklite_memory_read',
  'bklite_memory_write',
  'bklite_http_request',
  'bklite_notification',
]);

interface Props {
  atomKey: string;
  schema?: JsonSchema;
  value: Record<string, unknown>;
  references: DataReferenceOption[];
  workflowId: number | null;
  nodeTitle: string;
  readOnly: boolean;
  onChange: (value: Record<string, unknown>) => void;
  onNodeTitleChange: (value: string) => void;
}

interface KnowledgeReference {
  kind: 'workflow_agent_knowledge';
  name: string;
  format: 'md';
  size: number;
  token: string;
}

const field = (schema: JsonSchema | undefined, key: string): JsonSchema => schema?.properties?.[key] || { type: 'string', title: key };

function ResourceSelect({ schema, value, placeholder, disabled, onChange }: { schema: JsonSchema; value: unknown; placeholder: string; disabled: boolean; onChange: (value: unknown) => void }) {
  const { t } = useTranslation();
  const options = (schema.enum || []).map((item) => {
    const name = schema['x-enum-labels']?.[String(item)] || String(item);
    const metadata = schema['x-enum-metadata']?.[String(item)];
    return {
      value: item as string | number,
      title: name,
      label: metadata?.scope ? <div className="flex items-center justify-between gap-3"><span>{name}</span><span className="text-xs text-[var(--color-text-4)]">{metadata.scope === 'personal' ? t('workflowOrchestration.editor.personalScope', '个人') : t('workflowOrchestration.editor.teamScope', '团队')}</span></div> : name,
    };
  });
  return <Select className="w-full" showSearch optionFilterProp="title" allowClear disabled={disabled} value={value as string | number | undefined} options={options} placeholder={options.length ? placeholder : `${placeholder}${t('workflowOrchestration.editor.noAvailableOptions', '（暂无可用项）')}`} onChange={onChange} />;
}

function NodeNameField({ value, disabled, onChange }: { value: string; disabled: boolean; onChange: (value: string) => void }) {
  const { t } = useTranslation();
  return <Form.Item className="mb-0" label={t('workflowOrchestration.editor.nodeName', '节点名称')} required>
    <Input disabled={disabled} value={value} placeholder={t('workflowOrchestration.editor.enterNodeName', '请输入节点名称')} onChange={(event) => onChange(event.target.value)} />
  </Form.Item>;
}

interface KeyValueRow {
  key: string;
  value: unknown;
}

function keyValueRowsFromObject(objectValue: Record<string, unknown>): KeyValueRow[] {
  const entries = Object.entries(objectValue).map(([key, item]) => ({ key, value: item }));
  return entries.length > 0 ? entries : [{ key: '', value: '' }];
}

/** Match OpsPilot Chatflow HTTP key-value editor layout; keep SchemaNodeField for workflow references. */
function OpsPilotKeyValueRows({ label, value, references, disabled, onChange }: {
  label: string;
  value: unknown;
  references: DataReferenceOption[];
  disabled: boolean;
  onChange: (value: Record<string, unknown>) => void;
}) {
  const { t } = useTranslation();
  const objectValue = value && typeof value === 'object' && !Array.isArray(value) ? value as Record<string, unknown> : {};
  const fingerprint = JSON.stringify(objectValue);
  const [rows, setRows] = useState<KeyValueRow[]>(() => keyValueRowsFromObject(objectValue));

  useEffect(() => {
    setRows(keyValueRowsFromObject(objectValue));
    // fingerprint is the stable synchronization boundary for externally changed node inputs.
  }, [fingerprint]);

  const commit = (next: KeyValueRow[]) => onChange(Object.fromEntries(next.filter((item) => item.key.trim()).map((item) => [item.key.trim(), item.value])));
  const update = (index: number, patch: Partial<KeyValueRow>) => {
    const next = rows.map((item, itemIndex) => itemIndex === index ? { ...item, ...patch } : item);
    setRows(next);
    commit(next);
  };
  const addRow = () => {
    const next = [...rows, { key: '', value: '' }];
    setRows(next);
    commit(next);
  };
  const remove = (index: number) => {
    if (rows.length <= 1) return;
    const next = rows.filter((_, itemIndex) => itemIndex !== index);
    setRows(next);
    commit(next);
  };

  return (
    <Form.Item className="mb-0" label={label}>
      <div className="space-y-2">
        <div className="mb-1 grid grid-cols-[1fr_1fr_60px] gap-2 text-sm text-[var(--color-text-3)]">
          <span>{t('workflowOrchestration.editor.parameterName', '参数名')}</span>
          <span>{t('workflowOrchestration.editor.parameterValue', '参数值')}</span>
          <span>{t('workflowOrchestration.editor.operation', '操作')}</span>
        </div>
        {rows.map((row, index) => (
          <div key={index} className="grid grid-cols-[1fr_1fr_60px] items-center gap-2">
            <Input
              disabled={disabled}
              value={row.key}
              placeholder={t('workflowOrchestration.editor.enterParameterName', '输入参数名')}
              onChange={(event) => update(index, { key: event.target.value })}
            />
            <div className="flex min-w-0 items-center gap-1">
              <span className="shrink-0 rounded bg-[var(--color-fill-1)] px-1 text-xs text-[var(--color-text-3)]">str</span>
              <div className="min-w-0 flex-1">
                <SchemaNodeField
                  schema={{ type: 'string', 'x-placeholder': t('workflowOrchestration.editor.enterOrReferenceParameterValue', '输入或引用参数值') }}
                  value={row.value}
                  references={references}
                  onChange={(next) => update(index, { value: next })}
                />
              </div>
            </div>
            <div className="flex gap-1">
              <WorkflowPermission operation="Edit"><Button type="text" size="small" aria-label={t('workflowOrchestration.editor.addParameter', '添加参数')} icon={<PlusOutlined />} disabled={disabled} onClick={addRow} /></WorkflowPermission>
              <WorkflowPermission operation="Edit"><Button type="text" size="small" aria-label={t('workflowOrchestration.editor.removeParameter', '删除参数')} icon={<MinusOutlined />} disabled={disabled || rows.length <= 1} onClick={() => remove(index)} /></WorkflowPermission>
            </div>
          </div>
        ))}
      </div>
    </Form.Item>
  );
}

function HttpRequestFields({ schema, value, references, readOnly, onChange }: Pick<Props, 'schema' | 'value' | 'references' | 'readOnly' | 'onChange'>) {
  const { t } = useTranslation();
  const setField = (key: string, next: unknown) => onChange({ ...value, [key]: next });
  const methodSchema = field(schema, 'method');

  return <>
    <Form.Item className="mb-0" label="API" required>
      <div className="flex w-full items-center gap-2">
        <Select
          className="shrink-0"
          style={{ width: 104 }}
          disabled={readOnly}
          value={value.method as string | undefined}
          options={(methodSchema.enum || ['GET', 'POST', 'PUT', 'PATCH', 'DELETE']).map((item) => ({ value: String(item), label: String(item) }))}
          onChange={(next) => setField('method', next)}
        />
        <div className="min-w-0 flex-1">
          <SchemaNodeField
            schema={{ type: 'string', 'x-placeholder': t('workflowOrchestration.editor.enterUrl', '输入URL') }}
            value={value.url}
            references={references}
            disabled={readOnly}
            onChange={(next) => setField('url', next)}
          />
        </div>
      </div>
    </Form.Item>
    {schema?.properties?.query ? <OpsPilotKeyValueRows label={t('workflowOrchestration.editor.requestParameters', '请求参数')} value={value.query} references={references} disabled={readOnly} onChange={(next) => setField('query', next)} /> : null}
    {schema?.properties?.headers ? <OpsPilotKeyValueRows label={t('workflowOrchestration.editor.requestHeaders', '请求头')} value={value.headers} references={references} disabled={readOnly} onChange={(next) => setField('headers', next)} /> : null}
    {schema?.properties?.body ? <Form.Item className="mb-0" label={t('workflowOrchestration.editor.requestBody', '请求体')}><SchemaNodeField schema={{ ...field(schema, 'body'), 'x-widget': 'json', 'x-rows': 6, jsonEditorAllowed: true }} value={value.body} references={references} onChange={(next) => setField('body', next)} /></Form.Item> : null}
    {schema?.properties?.timeout ? <Form.Item className="mb-0" label={t('workflowOrchestration.editor.timeoutSeconds', '超时设置（秒）')}><InputNumber className="w-full" min={field(schema, 'timeout').minimum || 1} max={field(schema, 'timeout').maximum || 60} disabled={readOnly} value={typeof value.timeout === 'number' ? value.timeout : Number(field(schema, 'timeout').default || 30)} onChange={(next) => setField('timeout', next)} /></Form.Item> : null}
  </>;
}

function normalizeRecipientIds(value: unknown, items?: JsonSchema): string[] {
  if (!Array.isArray(value)) return [];
  const enumIds = new Set((items?.enum || []).map(String));
  const labels = items?.['x-enum-labels'] || {};
  const usernameToId = new Map<string, string>();
  for (const [id, label] of Object.entries(labels)) {
    const match = /\(([^)]+)\)$/.exec(String(label));
    if (match) usernameToId.set(match[1], id);
  }
  const usernames = items?.['x-enum-usernames'] || {};
  for (const [id, username] of Object.entries(usernames)) {
    usernameToId.set(String(username), String(id));
  }
  return value.map((item) => {
    const raw = String(item);
    if (enumIds.has(raw)) return raw;
    return usernameToId.get(raw) || raw;
  });
}

function NotificationFields({ schema, value, references, readOnly, onChange }: Pick<Props, 'schema' | 'value' | 'references' | 'readOnly' | 'onChange'>) {
  const { t } = useTranslation();
  const setField = (key: string, next: unknown) => onChange({ ...value, [key]: next });
  const typeSchema = field(schema, 'notification_type');
  const channelSchema = field(schema, 'channel_id');
  const recipientSchema = field(schema, 'recipients');
  const reportArtifactSchema = field(schema, 'report_artifact');
  const notificationType = String(value.notification_type || typeSchema.default || 'EMAIL');
  const typeOptions = (typeSchema.enum || ['EMAIL', 'WECOM_BOT', 'FEISHU_BOT', 'DINGTALK_BOT', 'CUSTOM_WEBHOOK']).map((item) => ({ value: item, label: typeSchema['x-enum-labels']?.[String(item)] || String(item) }));
  const channelOptions = (channelSchema.enum || []).map((item) => ({ value: item as string | number, label: channelSchema['x-enum-labels']?.[String(item)] || String(item) }));
  const recipientItems = recipientSchema.items;
  const normalizedRecipients = useMemo(
    () => normalizeRecipientIds(value.recipients, recipientItems),
    [recipientItems, value.recipients],
  );

  useEffect(() => {
    if (!Array.isArray(value.recipients)) return;
    const current = value.recipients.map(String);
    if (current.length === normalizedRecipients.length && current.every((item, index) => item === normalizedRecipients[index])) return;
    setField('recipients', normalizedRecipients);
  }, [normalizedRecipients, value.recipients]);

  return <>
    <Form.Item className="mb-0" label={t('workflowOrchestration.editor.notificationCategory', '通知类别')} required><Radio.Group disabled={readOnly} value={notificationType} options={typeOptions} onChange={(event) => onChange({ ...value, notification_type: event.target.value, channel_id: undefined })} /></Form.Item>
    <div className="relative">
      <Form.Item className="mb-0" label={t('workflowOrchestration.editor.notificationMethod', '通知方式')} required><Select showSearch optionFilterProp="label" allowClear disabled={readOnly} value={value.channel_id as string | number | undefined} options={channelOptions} placeholder={channelOptions.length ? t('workflowOrchestration.editor.selectNotificationMethod', '请选择通知方式') : t('workflowOrchestration.editor.noNotificationChannels', '暂无可用通知渠道')} onChange={(next) => setField('channel_id', next)} /></Form.Item>
      {!readOnly ? <Button className="absolute right-0 top-0 h-auto px-0 text-xs" type="link" size="small" icon={<PlusOutlined />} href="/system-manager/channel" target="_blank">{t('workflowOrchestration.editor.addNotificationChannel', '新增通知渠道')}</Button> : null}
    </div>
    {notificationType === 'EMAIL' && schema?.properties?.recipients ? <Form.Item className="mb-0" label={t('workflowOrchestration.editor.notificationPeople', '通知人')} required={schema.required?.includes('recipients')}><SchemaNodeField schema={recipientSchema} value={normalizedRecipients} references={references} onChange={(next) => setField('recipients', normalizeRecipientIds(next, recipientItems))} /></Form.Item> : null}
    {notificationType === 'EMAIL' && schema?.properties?.title ? <Form.Item className="mb-0" label={t('workflowOrchestration.editor.notificationTitle', '通知标题')} required={schema.required?.includes('title')}><SchemaNodeField schema={field(schema, 'title')} value={value.title} references={references} onChange={(next) => setField('title', next)} /></Form.Item> : null}
    {notificationType === 'EMAIL' && schema?.properties?.report_artifact ? (
      <Form.Item
        className="mb-0"
        label={t('workflowOrchestration.editor.notificationAttachment', '附件')}
        tooltip={t('workflowOrchestration.editor.notificationAttachmentHint', '可选，拖入上游报告产物')}
      >
        <SchemaNodeField
          schema={reportArtifactSchema}
          value={value.report_artifact}
          references={references}
          referenceOnly
          onChange={(next) => setField('report_artifact', next)}
        />
      </Form.Item>
    ) : null}
    {schema?.properties?.body ? <Form.Item className="mb-0" label={t('workflowOrchestration.editor.notificationContent', '通知内容')} required={schema.required?.includes('body')}><SchemaNodeField schema={{ ...field(schema, 'body'), 'x-widget': 'textarea', 'x-rows': 6 }} value={value.body} references={references} onChange={(next) => setField('body', next)} /></Form.Item> : null}
  </>;
}

function RuntimeFields({ keys, schema, value, references, onChange }: { keys: string[]; schema?: JsonSchema; value: Record<string, unknown>; references: DataReferenceOption[]; onChange: (value: Record<string, unknown>) => void }) {
  const { t } = useTranslation();
  return <Collapse ghost items={[{
    key: 'runtime-data',
    label: t('workflowOrchestration.editor.runtimeData', '运行数据'),
    children: <div className="flex flex-col gap-5">
      <Alert type="info" showIcon message={t('workflowOrchestration.editor.runtimeDataHint', '这里配置节点实际处理的数据，可填写固定值，也可从左侧拖入触发输入或上游结果。')} />
      {keys.map((key) => {
        const item = field(schema, key);
        return <Form.Item className="mb-0" key={key} label={item.title || key} required={schema?.required?.includes(key)}>
          <SchemaNodeField schema={item} value={value[key]} references={references} onChange={(next) => onChange({ ...value, [key]: next })} />
        </Form.Item>;
      })}
    </div>,
  }]} />;
}

function KnowledgeUpload({ workflowId, value, disabled, onChange }: { workflowId: number | null; value: unknown; disabled: boolean; onChange: (value: KnowledgeReference[]) => void }) {
  const { post } = useApiClient();
  const { message } = App.useApp();
  const { t } = useTranslation();
  const [uploading, setUploading] = useState(false);
  const references = useMemo(() => Array.isArray(value) ? value.filter((item): item is KnowledgeReference => (
    Boolean(item) && typeof item === 'object' && (item as KnowledgeReference).kind === 'workflow_agent_knowledge'
  )) : [], [value]);
  const fileList: UploadFile[] = references.map((item) => ({ uid: item.token, name: item.name, size: item.size, status: 'done', type: 'text/markdown' }));

  return <Form.Item className="mb-0" label={t('workflowOrchestration.editor.uploadKnowledge', '上传知识')} tooltip={t('workflowOrchestration.editor.uploadKnowledgeTooltip', 'Markdown 内容会在智能体执行时作为补充背景知识注入。')}>
    {!workflowId ? <Alert className="mb-3" type="info" showIcon message={t('workflowOrchestration.editor.saveBeforeKnowledgeUpload', '首次上传前请先保存流程草稿')} /> : null}
    <Upload.Dragger
      accept=".md"
      multiple
      maxCount={10}
      disabled={disabled || uploading}
      fileList={fileList}
      beforeUpload={async (file) => {
        if (!workflowId) {
          message.info(t('workflowOrchestration.editor.saveBeforeKnowledgeUpload', '首次上传前请先保存流程草稿'));
          return Upload.LIST_IGNORE;
        }
        if (!file.name.toLowerCase().endsWith('.md')) {
          message.error(t('workflowOrchestration.editor.onlyMarkdownKnowledge', '仅支持 .md 知识文件'));
          return Upload.LIST_IGNORE;
        }
        if (file.size > 10 * 1024 * 1024) {
          message.error(t('workflowOrchestration.editor.knowledgeFileTooLarge', '单个文件不能超过 10 MiB'));
          return Upload.LIST_IGNORE;
        }
        setUploading(true);
        try {
          const body = new FormData();
          body.append('file', file);
          const uploaded = await post<KnowledgeReference>(`${API}/workflows/${workflowId}/agent-knowledge-upload/`, body, { headers: { 'Content-Type': 'multipart/form-data' } });
          onChange([...references.filter((item) => item.token !== uploaded.token), uploaded]);
          message.success(t('workflowOrchestration.editor.knowledgeUploaded', '知识文件已上传'));
        } finally {
          setUploading(false);
        }
        return Upload.LIST_IGNORE;
      }}
      onRemove={(removed) => {
        onChange(references.filter((item) => item.token !== removed.uid));
        return true;
      }}
    >
      <p className="ant-upload-drag-icon"><InboxOutlined /></p>
      <p className="ant-upload-text">{t('workflowOrchestration.editor.knowledgeUploadHint', '点击或拖拽 Markdown 文件到此区域上传')}</p>
      <p className="ant-upload-hint">{t('workflowOrchestration.editor.knowledgeUploadDescription', '支持多个 .md 文件，单文件不超过 10 MiB，总大小不超过 20 MiB')}</p>
    </Upload.Dragger>
  </Form.Item>;
}

function IntentList({ value, disabled, onChange }: { value: unknown; disabled: boolean; onChange: (value: string[]) => void }) {
  const { t } = useTranslation();
  const intents = Array.isArray(value) && value.length ? value.map(String) : [t('workflowOrchestration.editor.defaultIntent', '默认意图')];
  const duplicate = new Set(intents.filter((item, index) => item.trim() && intents.findIndex((candidate) => candidate.trim() === item.trim()) !== index));
  return <section>
    <div className="mb-3 flex items-center justify-between border-b border-[var(--color-border-1)] pb-2">
      <span className="text-sm font-medium text-[var(--color-text-2)]">{t('workflowOrchestration.editor.intentClassification', '意图分类')}</span>
      <WorkflowPermission operation="Edit"><Button type="dashed" size="small" icon={<PlusOutlined />} disabled={disabled || intents.length >= 20} onClick={() => onChange([...intents, ''])}>{t('workflowOrchestration.editor.addIntent', '添加意图')}</Button></WorkflowPermission>
    </div>
    <div className="flex flex-col gap-3">
      {intents.map((intent, index) => {
        const invalid = !intent.trim() || duplicate.has(intent);
        return <div key={index} className="group relative">
          <div className="mb-2 flex items-center gap-2">
            <span className="flex h-6 w-6 items-center justify-center rounded-full bg-[var(--color-primary)] text-xs font-semibold text-white">{index + 1}</span>
            <span className="text-xs font-medium text-[var(--color-text-3)]">{t('workflowOrchestration.editor.intentNumber', '分类 {number}', { number: index + 1 })}</span>
          </div>
          <Input.TextArea
            rows={3}
            disabled={disabled}
            status={invalid ? 'error' : undefined}
            value={intent}
            placeholder={t('workflowOrchestration.editor.intentPlaceholder', '描述这个意图，例如：告警处理')}
            onChange={(event) => onChange(intents.map((item, itemIndex) => itemIndex === index ? event.target.value : item))}
          />
          {!disabled ? <WorkflowPermission operation="Edit"><Button className="absolute right-2 top-9 opacity-0 transition-opacity group-hover:opacity-100" type="text" danger size="small" aria-label={t('workflowOrchestration.editor.removeIntent', '删除意图')} icon={<DeleteOutlined />} disabled={intents.length === 1} onClick={() => onChange(intents.filter((_, itemIndex) => itemIndex !== index))} /></WorkflowPermission> : null}
          {invalid ? <div className="mt-1 text-xs text-[var(--color-fail)]">{!intent.trim() ? t('workflowOrchestration.editor.intentRequired', '请输入意图内容') : t('workflowOrchestration.editor.intentDuplicate', '意图内容不能重复')}</div> : null}
        </div>;
      })}
    </div>
  </section>;
}

export function OpsPilotAtomForm({ atomKey, schema, value, references, workflowId, nodeTitle, readOnly, onChange, onNodeTitleChange }: Props) {
  const { t } = useTranslation();
  const setField = (key: string, next: unknown) => onChange({ ...value, [key]: next });
  const resourceField = (key: string, label: string, placeholder: string, createLabel?: string, createHref?: string, onSelect?: (value: unknown) => void) => <div className="relative">
    <Form.Item className="mb-0" label={label} required={schema?.required?.includes(key)}>
      <ResourceSelect schema={field(schema, key)} value={value[key]} placeholder={placeholder} disabled={readOnly} onChange={onSelect || ((next) => setField(key, next))} />
    </Form.Item>
    {createLabel && createHref ? <Button className="absolute right-0 top-0 h-auto px-0 text-xs" type="link" size="small" icon={<PlusOutlined />} href={createHref} target="_blank">{createLabel}</Button> : null}
  </div>;

  return <Form className="flex flex-col gap-5" layout="vertical">
    <NodeNameField value={nodeTitle} disabled={readOnly} onChange={onNodeTitleChange} />
    {atomKey === 'bklite_agent' ? <>
      {resourceField('agent_id', t('workflowOrchestration.editor.selectAgent', '选择智能体'), t('workflowOrchestration.editor.pleaseSelectAgent', '请选择智能体'), t('workflowOrchestration.editor.addAgent', '新增智能体'), '/opspilot/skill')}
      <Form.Item className="mb-0" label={field(schema, 'prompt').title || t('workflowOrchestration.editor.prompt', 'Prompt')} tooltip={t('workflowOrchestration.editor.promptAppendTooltip', '这段提示词会附加到本次输入之前。')}>
        <SchemaNodeField schema={field(schema, 'prompt')} value={value.prompt} references={references} onChange={(next) => setField('prompt', next)} />
      </Form.Item>
      <KnowledgeUpload workflowId={workflowId} value={value.knowledge_files} disabled={readOnly} onChange={(next) => setField('knowledge_files', next)} />
      <RuntimeFields keys={['message', 'memory_context']} schema={schema} value={value} references={references} onChange={onChange} />
    </> : null}

    {atomKey === 'bklite_intent_classification' ? <>
      {resourceField('model_id', t('workflowOrchestration.editor.llmModel', 'LLM 模型'), t('workflowOrchestration.editor.pleaseSelectLlmModel', '请选择 LLM 模型'))}
      <Form.Item className="mb-0" label={field(schema, 'classification_rules').title || t('workflowOrchestration.editor.classificationRules', '分类规则')} tooltip={t('workflowOrchestration.editor.classificationRulesTooltip', '补充分类判断原则；留空时由模型根据意图描述判断。')}>
        <SchemaNodeField schema={field(schema, 'classification_rules')} value={value.classification_rules} references={references} onChange={(next) => setField('classification_rules', next)} />
      </Form.Item>
      <IntentList value={value.intents} disabled={readOnly} onChange={(next) => setField('intents', next)} />
      <RuntimeFields keys={['text']} schema={schema} value={value} references={references} onChange={onChange} />
    </> : null}

    {atomKey === 'bklite_memory_read' ? <>
      {resourceField('memory_space_id', t('workflowOrchestration.editor.selectMemorySpace', '选择记忆空间'), t('workflowOrchestration.editor.pleaseSelectMemorySpace', '请选择记忆空间'), t('workflowOrchestration.editor.addMemorySpace', '新增记忆空间'), '/opspilot/memory')}
      <Collapse ghost items={[{ key: 'memory-read-settings', label: t('workflowOrchestration.editor.advancedSettings', '高级设置'), children: <Form.Item className="mb-0" label={field(schema, 'top_k').title || t('workflowOrchestration.editor.resultCount', '返回条数')}><InputNumber className="w-full" min={field(schema, 'top_k').minimum} max={field(schema, 'top_k').maximum} disabled={readOnly} value={typeof value.top_k === 'number' ? value.top_k : 5} onChange={(next) => setField('top_k', next)} /></Form.Item> }]} />
      <RuntimeFields keys={['query']} schema={schema} value={value} references={references} onChange={onChange} />
    </> : null}

    {atomKey === 'bklite_memory_write' ? <>
      {resourceField('memory_space_id', t('workflowOrchestration.editor.selectMemorySpace', '选择记忆空间'), t('workflowOrchestration.editor.pleaseSelectMemorySpace', '请选择记忆空间'), t('workflowOrchestration.editor.addMemorySpace', '新增记忆空间'), '/opspilot/memory', (next) => {
        const configuredDefault = field(schema, 'memory_space_id')['x-enum-metadata']?.[String(next)]?.default_model;
        const matchingModel = field(schema, 'model_id').enum?.find((item) => String(item) === String(configuredDefault));
        onChange({ ...value, memory_space_id: next, ...(matchingModel !== undefined ? { model_id: matchingModel } : {}) });
      })}
      {resourceField('model_id', t('workflowOrchestration.editor.llmModel', 'LLM 模型'), t('workflowOrchestration.editor.pleaseSelectLlmModel', '请选择 LLM 模型'))}
      <Form.Item className="mb-0" label={field(schema, 'write_batch_size').title || t('workflowOrchestration.editor.memoryWriteBatchSize', '累积写入条数')} tooltip={t('workflowOrchestration.editor.memoryWriteBatchSizeTooltip', '用于控制记忆写入的分批大小，范围 1–500。')} required>
        <InputNumber className="w-full" min={1} max={500} precision={0} disabled={readOnly} value={typeof value.write_batch_size === 'number' ? value.write_batch_size : 30} onChange={(next) => setField('write_batch_size', next)} />
      </Form.Item>
      <RuntimeFields keys={['content', 'title']} schema={schema} value={value} references={references} onChange={onChange} />
    </> : null}

    {atomKey === 'bklite_http_request' ? <HttpRequestFields schema={schema} value={value} references={references} readOnly={readOnly} onChange={onChange} /> : null}

    {atomKey === 'bklite_notification' ? <NotificationFields schema={schema} value={value} references={references} readOnly={readOnly} onChange={onChange} /> : null}
  </Form>;
}
