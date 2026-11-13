'use client';

import { Button, Input, Popconfirm, message } from 'antd';
import { useCallback, useEffect, useRef, useState } from 'react';
import OperateModal from '@/components/operate-modal';
import CustomTable from '@/app/itsm/components/itsm-list-table';
import { useItsmApi } from '../../api/useItsmApi';
import { FieldRow } from '../../components/field-row';
import { useTranslation } from '@/utils/i18n';

interface NoticeItem {
  id: number;
  title: string;
  content: string;
  is_enabled: boolean;
}

export default function Page() {
  const { t } = useTranslation();
  const api = useItsmApi();
  const [items, setItems] = useState<NoticeItem[]>([]);
  const [open, setOpen] = useState(false);
  const [editing, setEditing] = useState<NoticeItem | null>(null);
  const [title, setTitle] = useState('');
  const [content, setContent] = useState('');
  const editorRef = useRef<HTMLDivElement>(null);

  const load = useCallback(async () => {
    const data = await api.listResources('announcements') as { items?: NoticeItem[] };
    setItems(data.items || []);
  }, [api.listResources]);

  useEffect(() => {
    if (!api.ready) {
      return;
    }
    void load().catch((error: unknown) => message.error(error instanceof Error ? error.message : t('itsm.ticket.loadFailed')));
  }, [api.ready, load]);

  const start = (item?: NoticeItem) => {
    setEditing(item || null);
    setTitle(item?.title || '');
    setContent(item?.content || '');
    setOpen(true);
    window.setTimeout(() => {
      if (editorRef.current) {
        editorRef.current.innerHTML = item?.content || '';
      }
    }, 0);
  };

  const save = async () => {
    const body = { title, content };
    if (editing) {
      await api.updateResource('announcements', editing.id, body);
    } else {
      await api.createResource('announcements', { ...body, is_enabled: true });
    }
    setOpen(false);
    message.success(editing ? t('itsm.portal.saved') : t('itsm.admin.publishedNotice'));
    await load();
  };

  return (
    <div className="flex flex-col gap-4">
      <div className="flex items-center justify-between rounded-lg border border-[var(--color-border)] bg-[var(--color-bg)] px-4 py-3">
        <div className="text-base font-semibold leading-tight text-[var(--color-text-1)]">{t('itsm.admin.notice')}</div>
        <Button type="primary" onClick={() => start()}>{t('itsm.common.create')}</Button>
      </div>
      <div className="rounded-lg border border-[var(--color-border)] bg-[var(--color-bg)] p-4">
        <CustomTable
          rowKey="id"
          dataSource={items}
          locale={{ emptyText: t('itsm.admin.emptyNotice') }}
          columns={[
            { title: t('itsm.admin.noticeTitle'), dataIndex: 'title', key: 'title' },
            { title: t('itsm.admin.content'), dataIndex: 'content', key: 'content', ellipsis: true },
            { title: t('itsm.admin.state'), key: 'enabled', render: (_value: unknown, item: NoticeItem) => (item.is_enabled ? t('itsm.admin.enable') : t('itsm.admin.disable')) },
            {
              title: t('itsm.ticket.action'),
              key: 'actions',
              render: (_value: unknown, item: NoticeItem) => (
                <span className="inline-flex gap-2">
                  <Button type="link" size="small" onClick={() => start(item)}>{t('itsm.common.edit')}</Button>
                  <Button type="link" size="small" onClick={() => {
                    void api.updateResource('announcements', item.id, { is_enabled: !item.is_enabled }).then(load);
                  }}>{item.is_enabled ? t('itsm.admin.disable') : t('itsm.admin.enable')}</Button>
                  <Popconfirm title={t('itsm.admin.deleteNotice')} onConfirm={() => { void api.deleteResource('announcements', item.id).then(load); }}>
                    <Button type="link" size="small" danger>{t('itsm.common.delete')}</Button>
                  </Popconfirm>
                </span>
              ),
            },
          ]}
        />
      </div>
      <OperateModal title={editing ? t('itsm.admin.editNotice') : t('itsm.admin.newNotice')} open={open} onCancel={() => setOpen(false)} onOk={() => { void save(); }}>
        <div className="flex flex-col gap-3">
          <FieldRow label={t('itsm.admin.noticeTitle')}>
            <Input placeholder={t('itsm.admin.noticeTitle')} value={title} onChange={(event) => setTitle(event.target.value)} />
          </FieldRow>
          <FieldRow label={t('itsm.admin.content')} align="start">
            <div className="flex flex-col gap-2">
              <div className="flex gap-2">
                <Button size="small" onClick={() => document.execCommand('bold')}>{t('itsm.admin.bold')}</Button>
                <Button size="small" onClick={() => {
                  const url = window.prompt(t('itsm.admin.imageUrl'));
                  if (url) {
                    document.execCommand('insertImage', false, url);
                  }
                }}>{t('itsm.admin.insertImage')}</Button>
              </div>
              <div
                ref={editorRef}
                className="min-h-32 rounded border border-[var(--color-border)] p-2 text-sm"
                contentEditable
                suppressContentEditableWarning
                onInput={(event) => setContent((event.target as HTMLDivElement).innerHTML)}
              />
            </div>
          </FieldRow>
        </div>
      </OperateModal>
    </div>
  );
}
