'use client';

import { ItsmListEntry } from '@/app/itsm/components/list-entry';

import { ItsmRowActions, ItsmListToolbar, ItsmCreateButton } from '@/app/itsm/components/list-controls';

import { Input, Select, Tag, message } from 'antd';
import { useCallback, useEffect, useState } from 'react';
import { ItsmModal as OperateModal } from '@/app/itsm/components/interaction-surfaces';
import CustomTable from '@/app/itsm/components/itsm-list-table';
import { useItsmApi } from '../../api/useItsmApi';
import { FieldRow } from '../../components/field-row';
import { useTranslation } from '@/utils/i18n';

interface TemplateItem {
  id: number;
  event: string;
  channel_type: 'site' | 'im';
  title_tpl: string;
  content_tpl: string;
  is_builtin: boolean;
}

const channels = [
  { value: 'site' as const, label: '站内通知' },
  { value: 'im' as const, label: '即时消息' },
];

export default function NotifyTemplatesPage() {
  const { t } = useTranslation();
  const api = useItsmApi();
  const [keyword, setKeyword] = useState('');
  const [items, setItems] = useState<TemplateItem[]>([]);
  const [canEdit, setCanEdit] = useState(false);
  const [saving, setSaving] = useState(false);
  const [open, setOpen] = useState(false);
  const [editing, setEditing] = useState<TemplateItem | null>(null);
  const [event, setEvent] = useState('');
  const [channel, setChannel] = useState<TemplateItem['channel_type']>('site');
  const [title, setTitle] = useState('');
  const [content, setContent] = useState('');

  const load = useCallback(async () => {
    const data = await api.listNotifyTemplates() as { items?: TemplateItem[]; can_edit?: boolean };
    setItems(data.items || []);
    setCanEdit(data.can_edit === true);
  }, [api.listNotifyTemplates]);

  useEffect(() => {
    if (!api.ready) {
      return;
    }
    void load().catch((error: unknown) => message.error(error instanceof Error ? error.message : t('itsm.ticket.loadFailed')));
  }, [api.ready, load]);

  const start = (item?: TemplateItem) => {
    setEditing(item || null);
    setEvent(item?.event || '');
    setChannel(item?.channel_type === 'im' ? 'im' : 'site');
    setTitle(item?.title_tpl || '');
    setContent(item?.content_tpl || '');
    setOpen(true);
  };

  const save = async () => {
    if (!event.trim() || !title.trim()) {
      message.warning(t('itsm.admin.needEvent'));
      return;
    }
    setSaving(true);
    try {
      await api.saveNotifyTemplate({ id: editing?.id, event: event.trim(), channel_type: channel, title_tpl: title.trim(), content_tpl: content });
      setOpen(false);
      message.success(editing ? t('itsm.portal.saved') : t('itsm.portal.created'));
      await load();
    } catch (error) {
      message.error(error instanceof Error ? error.message : t('itsm.ticket.loadFailed'));
    } finally {
      setSaving(false);
    }
  };

  const remove = async (id: number) => {
    try {
      await api.deleteNotifyTemplate(id);
      await load();
    } catch (error) {
      message.error(error instanceof Error ? error.message : t('itsm.ticket.loadFailed'));
    }
  };

  return (
    <div className="flex flex-col gap-4">
      <div className="rounded-lg border border-[var(--color-border)] bg-[var(--color-bg)] p-4">
        <ItsmListToolbar search={{ value: keyword, onChange: setKeyword, placeholder: '搜索名称或标识' }} actions={canEdit && <ItsmCreateButton onClick={() => start()} />} />
        <CustomTable queryKey={keyword}
          rowKey="id"
          dataSource={items.filter(item => `${item.event} ${item.title_tpl}`.toLowerCase().includes(keyword.trim().toLowerCase()))}
          locale={{ emptyText: t('itsm.admin.emptyNotify') }}
          columns={[
            { title: t('itsm.admin.event'), dataIndex: 'event', key: 'event', render: (value: string) => <Tag>{value}</Tag> },
            { title: '通知渠道', dataIndex: 'channel_type', key: 'channel_type', render: (value: string) => channels.find(item => item.value === value)?.label || value },
            { title: t('itsm.admin.noticeTitle'), dataIndex: 'title_tpl', key: 'title_tpl', render: (value: string, item: TemplateItem) => canEdit ? <ItsmListEntry onClick={() => start(item)}>{value}</ItsmListEntry> : value },
            ...(canEdit ? [{ fixed: 'right' as const, width: 120,
              title: t('itsm.ticket.action'),
              key: 'actions',
              render: (_value: unknown, item: TemplateItem) => <ItsmRowActions items={[{key: 'action-0', label: t('itsm.common.edit'), kind: 'edit' as const, onClick: () => start(item)},
                ...(item.is_builtin ? [] : [{key: 'action-1', label: t('itsm.common.delete'), kind: 'delete' as const, danger: true, confirm: {title: t('itsm.admin.deleteNotify'), content: undefined }, onClick: () => void remove(item.id)}])]} />,
            }] : []),
          ]}
        />
      </div>
      <OperateModal formValue={{event,channel,title,content}} title={editing ? t('itsm.admin.editNotify') : t('itsm.admin.newNotify')} open={open} onCancel={() => setOpen(false)} confirmLoading={saving} onOk={save}>
        <div className="flex flex-col gap-3">
          <FieldRow label={t('itsm.admin.event')}>
            <Input aria-label="事件标识" disabled={editing?.is_builtin} placeholder={t('itsm.admin.eventKey')} value={event} onChange={(input) => setEvent(input.target.value)} />
          </FieldRow>
          <FieldRow label="通知渠道">
            <Select aria-label="通知渠道" className="w-full" disabled={editing?.is_builtin} value={channel} options={channels} onChange={setChannel} />
          </FieldRow>
          <FieldRow label={t('itsm.admin.noticeTitle')}>
            <Input aria-label="通知标题" placeholder={t('itsm.admin.titleTpl')} value={title} onChange={(input) => setTitle(input.target.value)} />
          </FieldRow>
          <FieldRow label={t('itsm.admin.content')} align="start">
            <Input.TextArea aria-label="通知内容" rows={4} placeholder={t('itsm.admin.contentTpl')} value={content} onChange={(input) => setContent(input.target.value)} />
          </FieldRow>
          <p className="text-xs text-[var(--color-text-3)]">用 {'{{ title }}'}、{'{{ content }}'} 或 {'{{ url }}'} 引用事件提供的内容。</p>
        </div>
      </OperateModal>
    </div>
  );
}
