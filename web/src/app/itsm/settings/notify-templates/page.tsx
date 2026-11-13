'use client';

import { Button, Input, Popconfirm, Tag, message } from 'antd';
import { useCallback, useEffect, useState } from 'react';
import OperateModal from '@/components/operate-modal';
import CustomTable from '@/app/itsm/components/itsm-list-table';
import { useItsmApi } from '../../api/useItsmApi';
import { FieldRow } from '../../components/field-row';
import { useTranslation } from '@/utils/i18n';

interface TemplateItem {
  id: number;
  event: string;
  title_tpl: string;
  content_tpl: string;
  is_builtin: boolean;
}

export default function NotifyTemplatesPage() {
  const { t } = useTranslation();
  const api = useItsmApi();
  const [items, setItems] = useState<TemplateItem[]>([]);
  const [open, setOpen] = useState(false);
  const [editing, setEditing] = useState<TemplateItem | null>(null);
  const [event, setEvent] = useState('');
  const [title, setTitle] = useState('');
  const [content, setContent] = useState('');

  const load = useCallback(async () => {
    const data = await api.listNotifyTemplates() as { items?: TemplateItem[] };
    setItems(data.items || []);
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
    setTitle(item?.title_tpl || '');
    setContent(item?.content_tpl || '');
    setOpen(true);
  };

  const save = async () => {
    if (!event.trim() || !title.trim()) {
      message.warning(t('itsm.admin.needEvent'));
      return;
    }
    await api.saveNotifyTemplate({ id: editing?.id, event: event.trim(), title_tpl: title.trim(), content_tpl: content });
    setOpen(false);
    message.success(editing ? t('itsm.portal.saved') : t('itsm.portal.created'));
    await load();
  };

  return (
    <div className="flex flex-col gap-4">
      <div className="flex items-center justify-between rounded-lg border border-[var(--color-border)] bg-[var(--color-bg)] px-4 py-3">
        <div className="text-sm font-medium text-[var(--color-text-1)]">{t('itsm.admin.notify')}</div>
        <Button type="primary" onClick={() => start()}>{t('itsm.common.create')}</Button>
      </div>
      <div className="rounded-lg border border-[var(--color-border)] bg-[var(--color-bg)] p-4">
        <CustomTable
          rowKey="id"
          dataSource={items}
          locale={{ emptyText: t('itsm.admin.emptyNotify') }}
          columns={[
            { title: t('itsm.admin.event'), dataIndex: 'event', key: 'event', render: (value: string) => <Tag>{value}</Tag> },
            { title: t('itsm.admin.noticeTitle'), dataIndex: 'title_tpl', key: 'title_tpl' },
            {
              title: t('itsm.ticket.action'),
              key: 'actions',
              render: (_value: unknown, item: TemplateItem) => (
                <span className="inline-flex gap-2">
                  <Button type="link" size="small" onClick={() => start(item)}>{t('itsm.common.edit')}</Button>
                  {item.is_builtin ? null : (
                    <Popconfirm title={t('itsm.admin.deleteNotify')} onConfirm={() => { void api.deleteNotifyTemplate(item.id).then(load); }}>
                      <Button type="link" size="small" danger>{t('itsm.common.delete')}</Button>
                    </Popconfirm>
                  )}
                </span>
              ),
            },
          ]}
        />
      </div>
      <OperateModal title={editing ? t('itsm.admin.editNotify') : t('itsm.admin.newNotify')} open={open} onCancel={() => setOpen(false)} onOk={() => { void save(); }}>
        <div className="flex flex-col gap-3">
          <FieldRow label={t('itsm.admin.event')}>
            <Input placeholder={t('itsm.admin.eventKey')} value={event} onChange={(input) => setEvent(input.target.value)} />
          </FieldRow>
          <FieldRow label={t('itsm.admin.noticeTitle')}>
            <Input placeholder={t('itsm.admin.titleTpl')} value={title} onChange={(input) => setTitle(input.target.value)} />
          </FieldRow>
          <FieldRow label={t('itsm.admin.content')} align="start">
            <Input.TextArea rows={4} placeholder={t('itsm.admin.contentTpl')} value={content} onChange={(input) => setContent(input.target.value)} />
          </FieldRow>
        </div>
      </OperateModal>
    </div>
  );
}
