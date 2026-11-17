'use client';

import { Alert, Button, Select, Tabs, message } from 'antd';
import Link from 'next/link';
import { useParams } from 'next/navigation';
import { useCallback, useEffect, useRef, useState } from 'react';
import { useItsmApi } from '../../../api/useItsmApi';
import { useTranslation } from '@/utils/i18n';
import OperateModal from '@/components/operate-modal';
import { flattenNodeFields } from '../../../components/node-settings';
import { FlowDesigner } from '../../../components/flow-designer';
import { publishDesignedWorkflow } from '../../../components/publish-designed-workflow';
import { FormDesigner } from '../../../components/form-designer';
import { WorkflowPreview } from '../../../components/workflow-preview';
import { FormRenderer } from '../../../components/form-renderer';
import { DEMO_FLOW, type FlowDesign } from '../../../constants/demo-flow';
import type { FormFieldSchema, FormSchema } from '../../../types';

interface DesignPayload extends FlowDesign {
  locked?: boolean;
  form_id?: number | null;
  workflow_name?: string;
  version_no?: number;
}

const missing = (design: FlowDesign) => {
  const incoming = new Set(design.edges.map((edge) => edge.to));
  return design.nodes.filter((node) => node.type !== 'start' && !incoming.has(node.id)).map((node) => node.id)
    .concat(design.nodes.some((node) => node.type === 'end') ? [] : ['end']);
};

export default function WorkflowDesignerPage() {
  const { t } = useTranslation();
  const params = useParams<{ id: string }>();
  const workflowId = Number(params.id);
  const api = useItsmApi();
  const [name, setName] = useState('');
  const [versionNo, setVersionNo] = useState(0);
  const [locked, setLocked] = useState(false);
  const [formId, setFormId] = useState<number | null>(null);
  const [fields, setFields] = useState<FormFieldSchema[]>([]);
  const [design, setDesign] = useState<FlowDesign>(DEMO_FLOW);
  const [invalid, setInvalid] = useState<string[]>([]);
  const [tab, setTab] = useState('form');
  const [preview, setPreview] = useState(false);
  const [busy, setBusy] = useState(false);
  const [templateOpen, setTemplateOpen] = useState(false);
  const [templates, setTemplates] = useState<{id:number;name:string}[]>([]);
  const [templateId, setTemplateId] = useState<number>();
  const [templateSchema, setTemplateSchema] = useState<FormSchema>();
  const [formBase, setFormBase] = useState<Partial<FormSchema>>({});
  const [templateLoading, setTemplateLoading] = useState(false);
  const templateRequest = useRef(0);
  const openTemplates = async () => {
    templateRequest.current++; setTemplateOpen(true); setTemplateSchema(undefined); setTemplateId(undefined); setTemplateLoading(true);
    try { const result = await api.listForms() as {items:{id:number;name:string}[]}; setTemplates(result.items || []); }
    catch (error) { message.error(error instanceof Error ? error.message : '表单模板加载失败'); }
    finally { setTemplateLoading(false); }
  };
  const selectTemplate = async (id:number) => {
    const request = ++templateRequest.current;
    setTemplateId(id); setTemplateSchema(undefined); setTemplateLoading(true);
    try { const result = await api.getForm(id) as {schema:FormSchema}; if (request === templateRequest.current) setTemplateSchema(result.schema); }
    catch (error) { if (request === templateRequest.current) message.error(error instanceof Error ? error.message : '模板读取失败'); }
    finally { if (request === templateRequest.current) setTemplateLoading(false); }
  };

  const load = useCallback(async () => {
    const data = await api.getDesign(workflowId) as DesignPayload;
    setName(data.workflow_name || t('itsm.design.flowFallback'));
    setVersionNo(data.version_no || 0);
    setLocked(Boolean(data.locked));
    setFormId(data.form_id ?? null);
    if (data.nodes?.length) {
      setDesign({ nodes: data.nodes, edges: data.edges || [], settings: data.settings });
    }
    if (data.form_id) {
      const form = await api.getForm(data.form_id) as { schema?: FormSchema };
      setFields(form.schema?.fields || []);
      setFormBase(form.schema || {});
    }
  }, [api.getDesign, api.getForm, workflowId]);

  useEffect(() => {
    if (!api.ready || !workflowId) {
      return;
    }
    void load().catch((error: unknown) => message.error(error instanceof Error ? error.message : t('itsm.ticket.loadFailed')));
  }, [api.ready, load, workflowId]);

  const updateDesign = useCallback((next: FlowDesign) => setDesign((current) => ({ ...current, ...next })), []);

  const schema: FormSchema = { ...formBase, version: 1, fields };

  const ensureForm = async () => {
    if (formId) {
      return formId;
    }
    const created = await api.createForm({ name: t('itsm.design.formSuffix', undefined, { name }), key: `form_${workflowId}_${Date.now()}` }) as { id: number };
    await api.saveDesign(workflowId, { ...design, form_id: created.id } as FlowDesign & { form_id: number });
    setFormId(created.id);
    return created.id;
  };

  const save = async () => {
    setBusy(true);
    try {
      const id = await ensureForm();
      if (id) {
        await api.saveForm(id, schema);
      }
      if (!locked) {
        await api.saveDesign(workflowId, design);
      }
      message.success(locked ? t('itsm.design.lockedSave') : t('itsm.design.saved'));
      await load();
    } catch (error) {
      message.error(error instanceof Error ? error.message : t('itsm.design.saveFailed'));
    } finally {
      setBusy(false);
    }
  };

  const copyDesign = async () => {
    setBusy(true);
    try {
      await api.saveDesign(workflowId, design);
      message.success('已创建新草稿');
      await load();
    } catch (error) {
      message.error(error instanceof Error ? error.message : t('itsm.design.copyFailed'));
    } finally {
      setBusy(false);
    }
  };

  const publish = async () => {
    const ids = missing(design);
    setInvalid(ids);
    if (ids.length) {
      message.warning(t('itsm.design.unlinked'));
      setTab('flow');
      return;
    }
    setBusy(true);
    try {
      const id = await ensureForm();
      await publishDesignedWorkflow(api, workflowId, id, schema, design);
      message.success(t('itsm.design.published'));
      await load();
    } catch (error) {
      message.error(error instanceof Error ? error.message : t('itsm.design.publishFailed'));
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="flex h-full min-h-0 flex-col gap-2 overflow-hidden">
      <div className="sticky top-0 z-30 flex shrink-0 flex-wrap items-center justify-between gap-x-4 gap-y-2 rounded-lg border border-[var(--color-border-1)] bg-[var(--color-bg)] px-4 py-2 shadow-[0_1px_3px_rgba(0,0,0,0.03)]">
        <div className="flex items-center gap-3">
          <Link href="/itsm/workflow">
            <Button size="small">{t('itsm.common.back')}</Button>
          </Link>
          <div className="h-4 w-px bg-[var(--color-border)]" />
          <div className="flex items-center gap-2.5">
            <span className="text-sm font-medium text-[var(--color-text-1)]">{name}</span>
            <span className="rounded bg-[var(--color-fill-1)] px-2 py-0.5 text-xs font-medium text-[var(--color-text-2)]">
              V{versionNo || 1}
            </span>
            <span
              className={`rounded px-2 py-0.5 text-xs font-medium ${
                locked
                  ? 'bg-[var(--color-primary-bg-active)] text-[var(--color-primary)]'
                  : 'bg-[var(--color-fill-1)] text-[var(--color-text-3)]'
              }`}
            >
              {locked ? t('itsm.design.active') : t('itsm.design.draft')}
            </span>
          </div>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          <Button disabled={locked} onClick={()=>void openTemplates()}>选择表单模板</Button>
          <Button onClick={() => setPreview((current) => !current)}>{preview ? t('itsm.design.backDesign') : t('itsm.design.preview')}</Button>
          <div className="mx-1 h-4 w-px bg-[var(--color-border)]" />
          <Button loading={busy} disabled={locked} onClick={() => { void save(); }}>{t('itsm.common.save')}</Button>
          <Button loading={busy} disabled={!locked} onClick={() => { void copyDesign(); }}>新建草稿</Button>
          <Button type="primary" loading={busy} disabled={locked} onClick={() => { void publish(); }}>{t('itsm.design.publish')}</Button>
        </div>
      </div>
      <OperateModal title="从表单模板创建" open={templateOpen} width={900} onCancel={()=>{ templateRequest.current++; setTemplateOpen(false); }} confirmLoading={templateLoading} okButtonProps={{disabled:!templateSchema || templateLoading}} onOk={()=>{
        if (!templateSchema) return;
        setFormId(null); setFormBase(structuredClone(templateSchema)); setFields(structuredClone(templateSchema.fields));
        setDesign(current=>({...current,nodes:current.nodes.map(node=>({...node,field_perm:{}})),settings:{...current.settings,template_source_id:templateId}}));
        setTemplateOpen(false); message.success('已复制模板，请保存流程');
      }}>
        <Select className="w-full mb-4" aria-label="选择表单模板" showSearch optionFilterProp="label" loading={templateLoading} value={templateId} options={templates.map(item=>({value:item.id,label:item.name}))} onChange={id=>void selectTemplate(id)} />
        <Alert className="mb-4" type="info" showIcon message="复制后独立维护，不影响原模板。应用将替换当前表单并清空节点字段权限，请重新检查节点配置。" />
        {templateSchema && <FormRenderer key={templateId} schema={templateSchema} readOnly hideSubmit onSubmit={()=>undefined} />}
      </OperateModal>
      {locked ? (
        <Alert
          type="warning"
          showIcon
          message={t('itsm.design.lockedHint')}
        />
      ) : null}
      {preview ? (
        <WorkflowPreview schema={schema} design={design} />
      ) : (
        <div className="flex min-h-0 flex-1 flex-col overflow-hidden rounded-lg border border-[var(--color-border-1)] bg-[var(--color-bg)] px-3 pb-3 shadow-[0_1px_3px_rgba(0,0,0,0.03)]">
          <Tabs
            className="flex min-h-0 flex-1 flex-col [&_.ant-tabs-content]:h-full [&_.ant-tabs-content-holder]:min-h-0 [&_.ant-tabs-content-holder]:flex-1 [&_.ant-tabs-nav]:sticky [&_.ant-tabs-nav]:top-0 [&_.ant-tabs-nav]:z-20 [&_.ant-tabs-nav]:mb-2 [&_.ant-tabs-nav]:bg-[var(--color-bg)] [&_.ant-tabs-tabpane]:h-full"
            activeKey={tab}
            onChange={setTab}
            items={[
              {
                key: 'form',
                label: t('itsm.design.formTab'),
                children: (
                  <div className={`h-full ${locked ? 'pointer-events-none opacity-60' : ''}`}>
                    <FormDesigner fields={fields} onChange={setFields} />
                  </div>
                ),
              },
              {
                key: 'flow',
                label: t('itsm.design.flowTab'),
                children: (
                  <div className={`h-full ${locked ? 'pointer-events-none opacity-60' : ''}`}>
                    <FlowDesigner
                      design={design}
                      fields={flattenNodeFields(fields).map((field) => field.key)}
                      formFields={fields}
                      invalidNodeIds={invalid}
                      onChange={updateDesign}
                    />
                  </div>
                ),
              },
            ]}
          />
        </div>
      )}
    </div>
  );
}
