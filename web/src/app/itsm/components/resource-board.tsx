'use client';

import { Button, Input, Popconfirm, message } from 'antd';
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
      if (value.startsWith('{') || value.startsWith('[')) {
        body[field] = JSON.parse(value) as unknown;
      } else {
        body[field] = value;
      }
    });
    return body;
  };

  const save = () => {
    let body: Record<string, unknown>;
    try {
      body = readDraft();
    } catch {
      message.error('JSON 格式不正确');
      return;
    }
    if (!Object.keys(body).length) {
      message.warning('先填写一项再保存');
      return;
    }
    const request = editingId == null
      ? api.createResource(kind, body)
      : api.updateResource(kind, editingId, body);
    void request.then(() => {
      setDraft({});
      setEditingId(null);
      message.success(editingId == null ? '已新建' : '已保存');
      return load();
    }).catch((error: unknown) => message.error(error instanceof Error ? error.message : '保存失败'));
  };

  const startEdit = (item: Record<string, unknown>) => {
    const next: Record<string, string> = {};
    fields.forEach((field) => {
      const value = item[field];
      next[field] = value == null ? '' : typeof value === 'string' ? value : JSON.stringify(value);
    });
    setDraft(next);
    setEditingId(Number(item.id));
  };

  return (
    <div className="flex flex-col gap-4">
      <div className="flex flex-wrap items-center justify-between gap-3 rounded-lg border border-[var(--color-border)] bg-[var(--color-bg)] px-4 py-3">
        <div className="text-base font-semibold text-[var(--color-text-1)]">{title}</div>
        <div className="flex flex-wrap items-center gap-2">
          {fields.map((field) => (
            <Input
              key={field}
              className="w-40"
              placeholder={labelOf(field)}
              value={draft[field] || ''}
              onChange={(event) => setDraft((current) => ({ ...current, [field]: event.target.value }))}
            />
          ))}
          <Button type="primary" onClick={save}>{editingId == null ? createLabel : '保存'}</Button>
          {editingId == null ? null : (
            <Button onClick={() => { setEditingId(null); setDraft({}); }}>取消</Button>
          )}
        </div>
      </div>
      <div className="rounded-lg border border-[var(--color-border)] bg-[var(--color-bg)] p-4">
        <CustomTable
          rowKey="id"
          size="middle"
          loading={loading}
          dataSource={items}
          locale={{ emptyText: '暂无数据' }}
          columns={[
            ...fields.map((field) => ({
              title: labelOf(field),
              dataIndex: field,
              key: field,
              ellipsis: true,
              render: (value: unknown) => (value == null || value === '' ? '—' : typeof value === 'string' ? value : JSON.stringify(value)),
            })),
            ...(actions.length ? [{
              title: '操作',
              key: 'actions',
              width: 180,
              render: (_value: unknown, item: Record<string, unknown>) => (
                <span className="inline-flex gap-2">
                  {actions.includes('edit') ? (
                    <Button type="link" size="small" onClick={() => startEdit(item)}>编辑</Button>
                  ) : null}
                  {actions.includes('enable') ? (
                    <Button type="link" size="small" onClick={() => {
                      void api.updateResource(kind, Number(item.id), { is_enabled: !item.is_enabled }).then(() => {
                        message.success(item.is_enabled ? '已停用' : '已启用');
                        return load();
                      }).catch((error: unknown) => message.error(error instanceof Error ? error.message : '操作失败'));
                    }}>{item.is_enabled ? '停用' : '启用'}</Button>
                  ) : null}
                  {actions.includes('delete') ? (
                    <Popconfirm title="确定删除？" onConfirm={() => {
                      void api.deleteResource(kind, Number(item.id)).then(() => {
                        if (editingId === Number(item.id)) {
                          setEditingId(null);
                          setDraft({});
                        }
                        message.success('已删除');
                        return load();
                      }).catch((error: unknown) => message.error(error instanceof Error ? error.message : '删除失败'));
                    }}>
                      <Button type="link" size="small" danger>删除</Button>
                    </Popconfirm>
                  ) : null}
                </span>
              ),
            }] : []),
          ]}
        />
      </div>
    </div>
  );
}
