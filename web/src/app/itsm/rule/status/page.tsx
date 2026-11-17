'use client';

import { ItsmRowActions, ItsmListToolbar, ItsmCreateButton } from '@/app/itsm/components/list-controls';

import { Button, ColorPicker, Input, Select, message } from 'antd';
import { useCallback, useEffect, useState } from 'react';
import OperateModal from '@/components/operate-modal';
import CustomTable from '@/app/itsm/components/itsm-list-table';
import { useItsmApi } from '../../api/useItsmApi';
import { FieldRow } from '../../components/field-row';
import { useTranslation } from '@/utils/i18n';

interface StatusItem {
  id: number;
  key: string;
  name: string;
  color: string;
  description: string;
  kind: string;
}

interface TransitionItem {
  id: number;
  from_id: number;
  to_id: number;
  from_name: string;
  to_name: string;
  name: string;
}

const makeKey = () => `status_${Math.random().toString(36).slice(2, 9)}`;

export default function Page() {
  const { t } = useTranslation();
  const api = useItsmApi();
  const [keyword, setKeyword] = useState('');
  const [items, setItems] = useState<StatusItem[]>([]);
  const [transitions, setTransitions] = useState<TransitionItem[]>([]);
  const [open, setOpen] = useState(false);
  const [editing, setEditing] = useState<StatusItem | null>(null);
  const [name, setName] = useState('');
  const [key, setKey] = useState('');
  const [color, setColor] = useState('#1677ff');
  const [description, setDescription] = useState('');
  const [target, setTarget] = useState<number>();

  const load = useCallback(async () => {
    const [statusData, transitionData] = await Promise.all([
      api.listStatusAdmin() as Promise<{ items?: StatusItem[] }>,
      api.listTransitions() as Promise<{ items?: TransitionItem[] }>,
    ]);
    setItems(statusData.items || []);
    setTransitions(transitionData.items || []);
  }, [api.listStatusAdmin, api.listTransitions]);

  useEffect(() => {
    if (!api.ready) {
      return;
    }
    void load().catch((error: unknown) => message.error(error instanceof Error ? error.message : t('itsm.ticket.loadFailed')));
  }, [api.ready, load]);

  const start = (item?: StatusItem) => {
    setEditing(item || null);
    setName(item?.name || '');
    setKey(item?.key || makeKey());
    setColor(item?.color || '#1677ff');
    setDescription(item?.description || '');
    setTarget(undefined);
    setOpen(true);
  };

  const save = async () => {
    if (!name.trim()) {
      message.warning(t('itsm.rule.needStatus'));
      return;
    }
    if (editing) {
      await api.postStatus({ id: editing.id, name: name.trim(), color, description });
    } else {
      await api.postStatus({ key, name: name.trim(), color, description });
    }
    setOpen(false);
    message.success(editing ? t('itsm.portal.saved') : t('itsm.portal.created'));
    await load();
  };

  return (
    <div className="flex flex-col gap-4">
      <div className="rounded-lg border border-[var(--color-border)] bg-[var(--color-bg)] p-4">
        <ItsmListToolbar search={{ value: keyword, onChange: setKeyword, placeholder: '搜索名称或标识' }} actions={<ItsmCreateButton onClick={() => start()} />} />
        <CustomTable queryKey={keyword}
          rowKey="id"
          dataSource={items.filter(item => `${item.name}`.toLowerCase().includes(keyword.trim().toLowerCase()))}
          locale={{ emptyText: t('itsm.rule.emptyStatus') }}
          columns={[
            { title: t('itsm.portal.name'), dataIndex: 'name', key: 'name' },
            { title: t('itsm.rule.keyword'), dataIndex: 'key', key: 'key' },
            { title: t('itsm.rule.color'), dataIndex: 'color', key: 'color', render: (value: string) => <span className="inline-block h-3 w-3 rounded-full" style={{ background: value }} /> },
            { title: t('itsm.rule.kind'), dataIndex: 'kind', key: 'kind', render: (value: string) => value === 'builtin' ? t('itsm.rule.builtin') : t('itsm.rule.custom') },
            {
              title: t('itsm.rule.transitions'),
              key: 'transitions',
              render: (_value: unknown, item: StatusItem) => transitions.filter((row) => row.from_id === item.id).map((row) => row.to_name).join('、') || '—',
            },
            { fixed: 'right' as const, width: 120,
              title: t('itsm.ticket.action'),
              key: 'actions',
              render: (_value: unknown, item: StatusItem) => <ItsmRowActions items={[{key: 'action-0', label: t('itsm.common.edit'), kind: 'edit' as const, onClick: () => start(item)},
                ...(item.kind === 'builtin' ? [] : [{key: 'action-1', label: t('itsm.common.delete'), kind: 'delete' as const, danger: true, confirm: {title: t('itsm.rule.deleteStatus'), content: undefined }, onClick: () => { void api.deleteStatus(item.id).then(load); }}])]} />,
            },
          ]}
        />
      </div>
      <OperateModal title={editing ? t('itsm.rule.editStatus') : t('itsm.rule.newStatus')} open={open} onCancel={() => setOpen(false)} onOk={() => { void save(); }}>
        <div className="flex flex-col gap-3 text-sm">
          <FieldRow label={t('itsm.rule.statusName')}>
            <Input value={name} onChange={(event) => setName(event.target.value)} />
          </FieldRow>
          <FieldRow label={t('itsm.rule.keyword')}>
            <Input value={key} disabled />
          </FieldRow>
          <FieldRow label={t('itsm.rule.color')}>
            <ColorPicker value={color} onChange={(value) => setColor(value.toHexString())} />
          </FieldRow>
          <FieldRow label={t('itsm.rule.statusDesc')} align="start">
            <Input.TextArea maxLength={100} showCount value={description} onChange={(event) => setDescription(event.target.value)} />
          </FieldRow>
          {editing ? (
            <FieldRow label={t('itsm.rule.statusFlow')} align="start">
              <div className="flex flex-col gap-2">
                {transitions.filter((row) => row.from_id === editing.id).map((row) => (
                  <div key={row.id} className="flex items-center justify-between text-xs">
                    <span>{row.from_name} → {row.to_name}</span>
                    <ItsmRowActions items={[{key: 'delete',label:t('itsm.common.delete'),kind:'delete',danger:true,confirm:{title:'确定删除这个流转关系？'},onClick:()=>api.deleteTransition(row.id).then(load)}]} />
                  </div>
                ))}
                <div className="flex gap-2">
                  <Select className="flex-1" placeholder={t('itsm.rule.flowTo')} value={target} options={items.filter((item) => item.id !== editing.id).map((item) => ({ value: item.id, label: item.name }))} onChange={setTarget} />
                  <Button onClick={() => { if (target) { const next = items.find((item) => item.id === target); void api.createTransition({ from_id: editing.id, to_id: target, name: `${editing.name} → ${next?.name || ''}` }).then(load); } }}>{t('itsm.admin.add')}</Button>
                </div>
              </div>
            </FieldRow>
          ) : null}
        </div>
      </OperateModal>
    </div>
  );
}
