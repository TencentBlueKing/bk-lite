'use client';

import { ItsmListEntry } from '@/app/itsm/components/list-entry';

import { ItsmRowActions, ItsmListToolbar, ItsmCreateButton } from '@/app/itsm/components/list-controls';

import { Input, message } from 'antd';
import { ItsmModal as OperateModal } from '@/app/itsm/components/interaction-surfaces';
import { FieldRow } from './field-row';
import CustomTable from '@/app/itsm/components/itsm-list-table';
import { useCallback, useEffect, useState } from 'react';
import { useItsmApi } from '../api/useItsmApi';

interface ResourceBoardProps {
  title: string;
  kind: string;
  fields: string[];
  /** 只放 ITSM4 该列表真正有的行操作。 */
  actions?: Array<'edit' | 'delete' | 'enable'>;
  createLabel?: string;
}

const LABELS: Record<string, string> = {
  name: '名称',
  title: '标题',
  content: '内容',
  kind: '类型',
  prompt: '提示词',
  visitor: '访客',
  key: '标识',
  from_user: '交出人',
  to_user: '接收人',
  body: '模板内容',
  event: '事件',
  action: '动作',
  cron: '周期',
  username: '用户名',
  principal: '委托人',
  agent: '代理人',
  status: '状态',
};

const labelOf = (field: string) => LABELS[field] || field;

export function ResourceBoard({ title, kind, fields, actions = [], createLabel = '新建' }: ResourceBoardProps) {
  const api = useItsmApi();
  const [items, setItems] = useState<Array<Record<string, unknown>>>([]);
  const [draft, setDraft] = useState<Record<string, string>>({});
  const [editingId, setEditingId] = useState<number | null>(null);
  const [loading, setLoading] = useState(false);
  const [keyword, setKeyword] = useState('');
  const [open, setOpen] = useState(false);
  const [saving, setSaving] = useState(false);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const data = await api.listResources(kind) as { items?: Array<Record<string, unknown>> };
      setItems(data.items || []);
    } finally {
      setLoading(false);
    }
  }, [api.listResources, kind]);

  useEffect(() => {
    if (!api.ready) {
      return;
    }
    void load().catch((error: unknown) => message.error(error instanceof Error ? error.message : '加载失败'));
  }, [api.ready, load]);

  const readDraft = () => {
    const body: Record<string, unknown> = {};
    fields.forEach((field) => {
      const value = (draft[field] || '').trim();
      if (!value) {
        return;
      }
      body[field] = value;
    });
    return body;
  };

  const save = async () => {
    const body = readDraft();
    if (!Object.keys(body).length) {
      message.warning('先填写一项再保存');
      return;
    }
    setSaving(true);
    try {
      if (editingId == null) await api.createResource(kind, body);
      else await api.updateResource(kind, editingId, body);
      setOpen(false);
      setDraft({});
      setEditingId(null);
      message.success(editingId == null ? '已新建' : '已保存');
      await load();
    } catch (error) {
      message.error(error instanceof Error ? error.message : '保存失败');
    } finally {
      setSaving(false);
    }
  };

  const startEdit = (item: Record<string, unknown>) => {
    const next: Record<string, string> = {};
    fields.forEach((field) => {
      const value = item[field];
      next[field] = value == null ? '' : typeof value === 'string' ? value : JSON.stringify(value);
    });
    setOpen(true);
    setDraft(next);
    setEditingId(Number(item.id));
  };

  return (
    <div className="flex flex-col gap-4">
      <div className="rounded-lg border border-[var(--color-border)] bg-[var(--color-bg)] p-4">
        <ItsmListToolbar search={{ value: keyword, onChange: setKeyword, placeholder: `搜索${title}` }}
          actions={<ItsmCreateButton onClick={() => { setDraft({}); setEditingId(null); setOpen(true); }} />} />
        <CustomTable queryKey={keyword}
          rowKey="id"
          size="middle"
          loading={loading}
          dataSource={items.filter(item => fields.some(field => String(item[field] ?? '').toLowerCase().includes(keyword.trim().toLowerCase())))}
          locale={{ emptyText: '暂无数据' }}
          columns={[
            ...fields.map((field) => ({
              title: labelOf(field),
              dataIndex: field,
              key: field,
              ellipsis: true,
              render: (value: unknown, item: Record<string, unknown>) => {
                const text = value == null || value === '' ? '—' : typeof value === 'string' ? value : JSON.stringify(value);
                return (field === 'name' || field === 'title') && actions.includes('edit') ? <ItsmListEntry onClick={() => startEdit(item)}>{text}</ItsmListEntry> : text;
              },
            })),
            ...(actions.length ? [{ fixed: 'right' as const, width: 120,
              title: '操作',
              key: 'actions',

              render: (_value: unknown, item: Record<string, unknown>) => <ItsmRowActions items={[...(actions.includes('edit') ? [{key: 'action-0', label: "编辑", kind: 'edit' as const, onClick: () => startEdit(item)}] : []),
                ...(actions.includes('enable') ? [{key: 'action-1', label: item.is_enabled ? '停用' : '启用', kind: 'publish' as const, onClick: () => {
                  void api.updateResource(kind, Number(item.id), { is_enabled: !item.is_enabled }).then(() => {
                    message.success(item.is_enabled ? '已停用' : '已启用');
                    return load();
                  }).catch((error: unknown) => message.error(error instanceof Error ? error.message : '操作失败'));
                }}] : []),
                ...(actions.includes('delete') ? [{key: 'action-2', label: "删除", kind: 'delete' as const, danger: true, confirm: {title: "确定删除？", content: undefined }, onClick: () => {
                  void api.deleteResource(kind, Number(item.id)).then(() => {
                    if (editingId === Number(item.id)) {
                      setEditingId(null);
                      setDraft({});
                    }
                    message.success('已删除');
                    return load();
                  }).catch((error: unknown) => message.error(error instanceof Error ? error.message : '删除失败'));
                }}] : [])]} />,
            }] : []),
          ]}
        />
      </div>
      <OperateModal formValue={draft} title={editingId == null ? `${createLabel}${title}` : `编辑${title}`} open={open}
        confirmLoading={saving} onCancel={() => setOpen(false)} onOk={save}>
        <div className="flex flex-col gap-4">{fields.map(field => <FieldRow key={field} label={labelOf(field)}>
          {['content', 'body', 'prompt'].includes(field)
            ? <Input.TextArea aria-label={labelOf(field)} rows={4} value={draft[field] || ''} onChange={event => setDraft(current => ({ ...current, [field]: event.target.value }))} />
            : <Input aria-label={labelOf(field)} value={draft[field] || ''} onChange={event => setDraft(current => ({ ...current, [field]: event.target.value }))} />}
        </FieldRow>)}</div>
      </OperateModal>
    </div>
  );
}
