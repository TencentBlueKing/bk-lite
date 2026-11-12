'use client';

import { Button, Input, message } from 'antd';
import Link from 'next/link';
import { useParams, useRouter } from 'next/navigation';
import { useEffect, useState } from 'react';
import { useItsmApi } from '../../../api/useItsmApi';
import type { PortalData, PortalService } from '../../../types';

export default function ApplyPage() {
  const params = useParams<{ serviceId: string }>();
  const serviceId = Number(params.serviceId);
  const router = useRouter();
  const api = useItsmApi();
  const [service, setService] = useState<PortalService | null>(null);
  const [title, setTitle] = useState('申请服务器');
  const [templates, setTemplates] = useState<string[]>([]);
  const [busy, setBusy] = useState(false);
  const draftKey = `itsm-draft-${serviceId}`;
  const templateKey = `itsm-templates-${serviceId}`;

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
    if (!serviceId) {
      return;
    }
    const saved = window.localStorage.getItem(draftKey);
    if (saved) {
      setTitle(saved);
    }
    void api.loadDrafts().then((data) => {
      const items = (data as { items?: Record<string, string> }).items || {};
      const remote = items[String(serviceId)];
      if (remote) {
        setTitle(remote);
      }
    }).catch(() => undefined);
    const raw = window.localStorage.getItem(templateKey);
    if (!raw) {
      setTemplates([]);
      return;
    }
    try {
      const parsed = JSON.parse(raw) as unknown;
      setTemplates(Array.isArray(parsed) ? parsed.filter((item): item is string => typeof item === 'string') : []);
    } catch {
      setTemplates([]);
    }
  }, [api.loadDrafts, draftKey, serviceId, templateKey]);

  const submit = async () => {
    if (!service?.version_id) {
      message.warning('服务还没有已发布的流程');
      return;
    }
    setBusy(true);
    try {
      await api.useService(service.id);
      const created = await api.createTicket({
        workflow_version_id: service.version_id,
        form_data: { title },
        service_id: service.id,
      }) as { id: number; sn: string };
      window.localStorage.removeItem(draftKey);
      message.success(`已提交 ${created.sn}`);
      router.push(`/itsm/tickets/${created.id}`);
    } catch (error) {
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
        <div className="flex flex-col gap-1.5">
          <span className="text-sm font-medium text-[var(--color-text-1)]">工单标题</span>
          <Input
            placeholder="请输入工单标题"
            value={title}
            onChange={(event) => {
              setTitle(event.target.value);
              window.localStorage.setItem(draftKey, event.target.value);
            }}
          />
        </div>
        {templates.length ? (
          <div className="flex flex-wrap gap-2">
            {templates.map((item) => (
              <Button key={item} size="small" onClick={() => setTitle(item)}>{item}</Button>
            ))}
          </div>
        ) : null}
        <div className="flex justify-end gap-2 border-t border-[var(--color-border)] pt-4">
          <Button
            onClick={() => {
              const next = [title, ...templates.filter((item) => item !== title)].slice(0, 5);
              setTemplates(next);
              window.localStorage.setItem(templateKey, JSON.stringify(next));
              window.localStorage.setItem(draftKey, title);
              void api.saveDraft({ service_id: serviceId, title });
              message.success('已保存提单模板');
            }}
          >
            存为模板
          </Button>
          <Button type="primary" loading={busy} onClick={() => { void submit(); }}>提交申请</Button>
        </div>
      </div>
    </div>
  );
}
