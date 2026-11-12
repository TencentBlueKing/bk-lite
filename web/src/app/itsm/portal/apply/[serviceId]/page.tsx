'use client';

import { Button, Form, message } from 'antd';
import Link from 'next/link';
import { useSession } from 'next-auth/react';
import { useParams, useRouter } from 'next/navigation';
import { useEffect, useState } from 'react';
import { useItsmApi } from '../../../api/useItsmApi';
import { FormRenderer } from '../../../components/form-renderer';
import type { FormSchema, PortalData, PortalService } from '../../../types';

export default function ApplyPage() {
  const params = useParams<{ serviceId: string }>();
  const serviceId = Number(params.serviceId);
  const router = useRouter();
  const api = useItsmApi();
  const { data: session } = useSession();
  const ownerKey = session?.user.id;
  const [service, setService] = useState<PortalService | null>(null);
  const [form] = Form.useForm();
  const [schema, setSchema] = useState<FormSchema>({ version: 1, fields: [] });
  const [fieldPerm, setFieldPerm] = useState<Record<string, 'hidden' | 'read' | 'edit'>>({});
  const [templates, setTemplates] = useState<Record<string, unknown>[]>([]);
  const [busy, setBusy] = useState(false);
  const draftKey = `itsm-draft-${ownerKey}-${serviceId}`;
  const templateKey = `itsm-templates-${ownerKey}-${serviceId}`;

  useEffect(() => {
    if (!api.ready || !serviceId) {
      return;
    }
    void api.portal().then((data) => {
      const portal = data as PortalData;
      setService(portal.services.find((item) => item.id === serviceId) || null);
    }).catch((error: unknown) => {
      message.error(error instanceof Error ? error.message : '加载失败');
    });
  }, [api.portal, api.ready, serviceId]);

  useEffect(() => {
    if (!serviceId || !api.ready || !ownerKey) {
      return;
    }
    const saved = window.localStorage.getItem(draftKey);
    if (saved) {
      try { form.setFieldsValue(JSON.parse(saved)); } catch { form.setFieldsValue({ title: saved }); }
    }
    void api.loadDrafts().then((data) => {
      const items = (data as { items?: Record<string, Record<string, unknown> | string> }).items || {};
      const remote = items[String(serviceId)];
      if (remote) {
        form.setFieldsValue(typeof remote === 'string' ? { title: remote } : remote);
      }
    }).catch(() => undefined);
    const raw = window.localStorage.getItem(templateKey);
    if (!raw) {
      setTemplates([]);
      return;
    }
    try {
      const parsed = JSON.parse(raw) as unknown;
      setTemplates(Array.isArray(parsed) ? parsed.map((item) => typeof item === 'string' ? { title: item } : item).filter((item): item is Record<string, unknown> => Boolean(item && typeof item === 'object' && !Array.isArray(item))) : []);
    } catch {
      setTemplates([]);
    }
  }, [api.loadDrafts, api.ready, ownerKey, draftKey, serviceId, templateKey, form]);

  useEffect(() => {
    if (!service?.version_id) return;
    void api.ticketForm(service.version_id).then((data) => {
      const result = data as { schema: FormSchema; field_perm: Record<string, 'hidden' | 'read' | 'edit'> };
      setSchema(result.schema);
      setFieldPerm(result.field_perm);
    }).catch(() => message.error('加载申请表单失败'));
  }, [api.ticketForm, service?.version_id]);

  const submit = async () => {
    if (!service?.version_id) {
      message.warning('服务还没有已发布的流程');
      return;
    }
    setBusy(true);
    try {
      const values = await form.validateFields();
      await api.useService(service.id);
      const created = await api.createTicket({
        workflow_version_id: service.version_id,
        form_data: values,
        service_id: service.id,
      }) as { id: number; sn: string };
      window.localStorage.removeItem(draftKey);
      void api.saveDraft({ service_id: serviceId, clear: true }).catch(() => message.warning('工单已提交，远端草稿清理失败'));
      message.success(`已提交 ${created.sn}`);
      router.push(`/itsm/tickets/${created.id}`);
    } catch (error) {
      if (error && typeof error === 'object' && 'errorFields' in error) return;
      message.error(error instanceof Error ? error.message : '提交失败');
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="flex flex-col gap-4">
      <div className="flex items-center justify-between rounded-lg border border-[var(--color-border)] bg-[var(--color-bg)] px-4 py-3">
        <div className="flex items-center gap-3">
          <Link href="/itsm/portal">
            <Button size="small">返回门户</Button>
          </Link>
          <div className="h-4 w-px bg-[var(--color-border)]" />
          <div className="flex flex-col">
            <span className="text-base font-medium text-[var(--color-text-1)]">{service?.name || '服务申请'}</span>
            {service?.description ? (
              <span className="text-xs text-[var(--color-text-3)]">{service.description}</span>
            ) : null}
          </div>
        </div>
      </div>

      <div className="flex max-w-2xl flex-col gap-4 rounded-lg border border-[var(--color-border)] bg-[var(--color-bg)] p-6">
        <FormRenderer form={form} schema={schema} fieldPerm={fieldPerm} hideSubmit onSubmit={() => undefined} />
        {templates.length ? (
          <div className="flex flex-wrap gap-2">
            {templates.map((item, index) => (
              <Button key={index} size="small" onClick={() => { form.resetFields(); form.setFieldsValue(item); }}>{String(item.title || `模板 ${index + 1}`)}</Button>
            ))}
          </div>
        ) : null}
        <div className="flex justify-end gap-2 border-t border-[var(--color-border)] pt-4">
          <Button disabled={!ownerKey || !schema.fields.length}
            onClick={() => {
              const values = form.getFieldsValue(true);
              const next = [values, ...templates].slice(0, 5);
              setTemplates(next);
              window.localStorage.setItem(templateKey, JSON.stringify(next));
              window.localStorage.setItem(draftKey, JSON.stringify(values));
              void api.saveDraft({ service_id: serviceId, form_data: values }).catch(() => message.warning('本地已保存，远端草稿保存失败'));
              message.success('已保存提单模板');
            }}
          >
            存为模板
          </Button>
          <Button type="primary" loading={busy} disabled={!schema.fields.length} onClick={() => { void submit(); }}>提交申请</Button>
        </div>
      </div>
    </div>
  );
}
