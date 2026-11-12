'use client';

import { Alert, Button, Tabs, message } from 'antd';
import Link from 'next/link';
import { useParams } from 'next/navigation';
import { useCallback, useEffect, useState } from 'react';
import { useItsmApi } from '../../../api/useItsmApi';
import { useTranslation } from '@/utils/i18n';
import { FlowDesigner } from '../../../components/flow-designer';
import { FormDesigner } from '../../../components/form-designer';
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
    }
  }, [api.getDesign, api.getForm, workflowId]);

  useEffect(() => {
    if (!api.ready || !workflowId) {
      return;
    }
    void load().catch((error: unknown) => message.error(error instanceof Error ? error.message : t('itsm.ticket.loadFailed')));
  }, [api.ready, load, workflowId]);

  const updateDesign = useCallback((next: FlowDesign) => setDesign((current) => ({ ...current, ...next })), []);

  const schema: FormSchema = { version: 1, fields };

  const saveForm = async () => {
    if (!formId) {
      return;
    }
    await api.saveForm(formId, schema);
  };

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
      message.success(t('itsm.design.copied'));
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
      await saveForm();
      if (!locked) {
        await api.saveDesign(workflowId, design);
      }
      await api.publishWorkflow(workflowId);
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
          <Button onClick={() => setPreview((current) => !current)}>{preview ? t('itsm.design.backDesign') : t('itsm.design.preview')}</Button>
          <div className="mx-1 h-4 w-px bg-[var(--color-border)]" />
          <Button loading={busy} onClick={() => { void save(); }}>{t('itsm.common.save')}</Button>
          <Button loading={busy} onClick={() => { void copyDesign(); }}>{t('itsm.design.copyFlow')}</Button>
          <Button type="primary" loading={busy} disabled={locked} onClick={() => { void publish(); }}>{t('itsm.design.publish')}</Button>
        </div>
      </div>
      {locked ? (
        <Alert
          type="warning"
          showIcon
          message={t('itsm.design.lockedHint')}
        />
      ) : null}
      {preview ? (
        <div className="min-h-0 flex-1 overflow-y-auto rounded-lg border border-[var(--color-border-1)] bg-[var(--color-fill-1)] p-4">
          <div className="mx-auto max-w-4xl rounded-lg border border-[var(--color-border-1)] bg-[var(--color-bg)] p-4 shadow-[0_1px_3px_rgba(0,0,0,0.03)]">
            <FormRenderer schema={schema} onSubmit={() => undefined} />
          </div>
        </div>
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
                      fields={fields.map((field) => field.key)}
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
