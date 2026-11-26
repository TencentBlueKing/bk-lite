'use client';

import { useCallback, useEffect, useRef, useState } from 'react';
import { App } from 'antd';
import { v4 as uuidv4 } from 'uuid';
import type { FormInstance } from 'antd';
import { useRouter } from 'next/navigation';
import { NODE_PALETTE } from '../constants/node-catalog';
import { useItsmApi } from '../api/useItsmApi';
import type { FormSchema, PortalData, PortalService, TicketDetail, TicketProgressEdge, TicketProgressNode } from '../types';

interface Preview { schema: FormSchema; field_perm: Record<string, 'hidden' | 'read' | 'edit'>; creator: string; workflow_name: string; nodes: TicketProgressNode[]; edges: TicketProgressEdge[] }

/** 新建态沿用详情布局；浏览服务不产生工单或启动流程。 */
export function useServiceDraft(serviceId: number | undefined, form: FormInstance, fromTicketCenter?: boolean) {
  const api = useItsmApi();
  const router = useRouter();
  const { message } = App.useApp();
  const [ticket, setTicket] = useState<TicketDetail | null>(null);
  const [service, setService] = useState<PortalService>();
  const [fieldPerm, setFieldPerm] = useState<Preview['field_perm']>({});
  const [error, setError] = useState('');
  const [busy, setBusy] = useState(false);
  const lock = useRef(false);
  const createdId = useRef<number | undefined>(undefined);
  const load = useCallback(async () => {
    if (!serviceId) return;
    setError('');
    try {
      const portal = await api.portal(serviceId) as PortalData;
      const chosen = portal.services.find(item => item.id === serviceId);
      if (!chosen?.version_id || portal.can_apply === false) throw new Error('服务已停用或你没有申请权限');
      const [preview, saved] = await Promise.all([
        api.ticketForm(chosen.version_id, serviceId) as Promise<Preview>,
        api.loadDrafts() as Promise<{ items?: Record<string, Record<string, unknown> | string> }>,
      ]);
      const draft = saved.items?.[String(serviceId)];
      const values = typeof draft === 'string' ? { title: draft } : draft || {};
      setService(chosen); setFieldPerm(preview.field_perm);
      setTicket({ id: 0, sn: '', status: 'new', title: chosen.name, creator: preview.creator, workflow_name: preview.workflow_name, form_data: values, fields: preview.schema.fields, form_rules: preview.schema.rules, tasks: [], nodes: preview.nodes.map(node => ({ ...node, name: node.name === node.id ? NODE_PALETTE.find(item => item.type === node.type)?.label || node.name : node.name })), edges: preview.edges, logs: [] });
    } catch (reason) { setError(reason instanceof Error ? reason.message : '加载服务失败'); }
  }, [api.portal, api.ticketForm, api.loadDrafts, serviceId]);
  useEffect(() => { if (api.ready && serviceId) void load(); }, [api.ready, serviceId, load]);
  const detailUrl = (id: number) => `/itsm/tickets/${id}${fromTicketCenter ? '?from=tickets' : ''}`;
  const save = async (submit: boolean) => {
    if (!serviceId || !service?.version_id || lock.current) return;
    if (createdId.current) { router.replace(detailUrl(createdId.current)); return; }
    lock.current = true; setBusy(true);
    try {
      const values = submit ? await form.validateFields() : form.getFieldsValue(true);
      if (!submit) {
        await api.saveDraft({ service_id: serviceId, form_data: values });
        message.success('草稿已保存');
        return;
      }
      const storageKey = `itsm:ticket-creation:${ticket?.creator}:${serviceId}`;
      const creationKey = sessionStorage.getItem(storageKey) || uuidv4();
      sessionStorage.setItem(storageKey, creationKey);
      const created = await api.createTicket({ workflow_version_id: service.version_id, service_id: serviceId, form_data: values, creation_key: creationKey }) as { id: number };
      createdId.current = created.id;
      sessionStorage.removeItem(storageKey);
      // 工单已创建后，辅助记录失败不能触发再次创建。
      void api.useService(serviceId).catch(() => undefined);
      void api.saveDraft({ service_id: serviceId, clear: true }).catch(() => message.warning('工单已创建，草稿清理失败'));
      router.replace(detailUrl(created.id));
    } catch (reason) {
      if (reason && typeof reason === 'object' && 'errorFields' in reason) {
        const invalid = (reason as { errorFields: { errors?: string[]; name?: string[] }[] }).errorFields[0];
        if (invalid?.errors?.[0]) message.warning(invalid.errors[0]);
      } else message.error(reason instanceof Error ? reason.message : '保存失败');
    } finally { lock.current = false; setBusy(false); }
  };
  return { ticket, fieldPerm, error, busy, load, save };
}
