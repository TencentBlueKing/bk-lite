'use client';

import { Button, Input, message } from 'antd';
import Link from 'next/link';
import { useCallback, useEffect, useState } from 'react';
import OperateModal from '@/components/operate-modal';
import CustomTable from '@/components/custom-table';
import { useItsmApi } from '../../api/useItsmApi';
import { FieldRow } from '../../components/field-row';
import { useTranslation } from '@/utils/i18n';

interface DictionaryItem {
  id: number;
  key: string;
  name: string;
}

interface EntryItem {
  id: number;
  key: string;
  label: string;
}

export default function DictionariesPage() {
  const { t } = useTranslation();
  const api = useItsmApi();
  const [items, setItems] = useState<DictionaryItem[]>([]);
  const [name, setName] = useState('');
  const [dictKey, setDictKey] = useState('');
  const [current, setCurrent] = useState<DictionaryItem | null>(null);
  const [entries, setEntries] = useState<EntryItem[]>([]);
  const [entryKey, setEntryKey] = useState('');
  const [entryLabel, setEntryLabel] = useState('');
  const [createOpen, setCreateOpen] = useState(false);
  const [editing, setEditing] = useState<DictionaryItem | null>(null);

  const load = useCallback(async () => {
    const data = await api.listDictionaries() as { items?: DictionaryItem[] };
    setItems(data.items || []);
  }, [api.listDictionaries]);

  useEffect(() => {
    if (!api.ready) {
      return;
    }
    void load().catch((error: unknown) => message.error(error instanceof Error ? error.message : t('itsm.ticket.loadFailed')));
  }, [api.ready, load]);

  const openItems = async (item: DictionaryItem) => {
    setCurrent(item);
    const data = await api.listDictionaryItems(item.id) as { items?: EntryItem[] };
    setEntries(data.items || []);
  };

  const exportFile = async () => {
    const rows = await api.exportDictionaries();
    const blob = new Blob([JSON.stringify(rows, null, 2)], { type: 'application/json' });
    const link = document.createElement('a');
    link.href = URL.createObjectURL(blob);
    link.download = 'dictionaries.json';
    link.click();
  };

  const create = async () => {
    if (!name.trim() || (!editing && !dictKey.trim())) {
      message.warning(t('itsm.admin.needDict'));
      return;
    }
    if (editing) {
      await api.createDictionary({ id: editing.id, name: name.trim() });
    } else {
      await api.createDictionary({ key: dictKey.trim(), name: name.trim() });
    }
    setName('');
    setDictKey('');
    setEditing(null);
    setCreateOpen(false);
    await load();
  };

  return (
    <div className="flex flex-col gap-4">
      <div className="flex flex-wrap items-center justify-between gap-4 rounded-lg border border-[var(--color-border)] bg-[var(--color-bg)] p-4">
        <div className="flex items-center gap-3">
          <Link href="/itsm/form">
            <Button size="small">{t('itsm.admin.backForms')}</Button>
          </Link>
          <div className="h-4 w-px bg-[var(--color-border)]" />
          <div className="text-base font-semibold leading-tight text-[var(--color-text-1)]">{t('itsm.admin.dictionary')}</div>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          <Button type="primary" onClick={() => { setEditing(null); setName(''); setDictKey(''); setCreateOpen(true); }}>{t('itsm.admin.newDictionary')}</Button>
          <Button onClick={() => { void exportFile(); }}>{t('itsm.admin.exportAll')}</Button>
          <Button>
            <label className="cursor-pointer">
              {t('itsm.admin.import')}
              <input
                className="hidden"
                type="file"
                accept="application/json"
                onChange={(event) => {
                  const file = event.target.files?.[0];
                  if (!file) {
                    return;
                  }
                  void file.text().then((text) => api.importDictionaries(JSON.parse(text) as unknown[])).then(load).catch(() => message.error(t('itsm.admin.importFailed')));
                }}
              />
            </label>
          </Button>
        </div>
      </div>

      <div className="rounded-lg border border-[var(--color-border)] bg-[var(--color-bg)] p-4">
        <CustomTable
          rowKey="id"
          dataSource={items}
          locale={{ emptyText: t('itsm.admin.emptyDictionary') }}
          columns={[
            { title: t('itsm.portal.name'), dataIndex: 'name', key: 'name' },
            { title: t('itsm.admin.key'), dataIndex: 'key', key: 'key' },
            {
              title: t('itsm.ticket.action'),
              key: 'actions',
              render: (_value: unknown, item: DictionaryItem) => (
                <span className="inline-flex gap-2">
                  <Button type="link" size="small" onClick={() => { setEditing(item); setName(item.name); setDictKey(item.key); setCreateOpen(true); }}>{t('itsm.common.edit')}</Button>
                  <Button type="link" size="small" onClick={() => { void openItems(item); }}>{t('itsm.admin.items')}</Button>
                </span>
              ),
            },
          ]}
        />
      </div>
      <OperateModal title={editing ? t('itsm.admin.editDictionary') : t('itsm.admin.newDictionaryTitle')} open={createOpen} onCancel={() => setCreateOpen(false)} onOk={() => { void create(); }}>
        <div className="flex flex-col gap-3 text-sm">
          <FieldRow label={t('itsm.admin.dictName')}>
            <Input value={name} onChange={(event) => setName(event.target.value)} />
          </FieldRow>
          <FieldRow label={t('itsm.admin.dictKey')}>
            <Input value={dictKey} disabled={Boolean(editing)} onChange={(event) => setDictKey(event.target.value)} />
          </FieldRow>
        </div>
      </OperateModal>
      {current ? (
        <div className="rounded-lg border border-[var(--color-border)] bg-[var(--color-bg)] p-4">
          <div className="mb-3 text-sm font-medium text-[var(--color-text-1)]">{t('itsm.admin.dictItems', undefined, { name: current.name })}</div>
          <div className="mb-3 flex gap-2">
            <Input className="w-32" placeholder={t('itsm.admin.itemKey')} value={entryKey} onChange={(event) => setEntryKey(event.target.value)} />
            <Input className="w-40" placeholder={t('itsm.admin.itemLabel')} value={entryLabel} onChange={(event) => setEntryLabel(event.target.value)} />
            <Button type="primary" onClick={() => {
              void api.createDictionaryItem(current.id, { key: entryKey, label: entryLabel }).then(() => openItems(current));
            }}>{t('itsm.admin.add')}</Button>
          </div>
          <CustomTable
            rowKey="id"
            dataSource={entries}
            pagination={false}
            locale={{ emptyText: t('itsm.admin.emptyItems') }}
            columns={[
              { title: t('itsm.admin.itemLabel'), dataIndex: 'label', key: 'label' },
              { title: t('itsm.admin.itemKey'), dataIndex: 'key', key: 'key' },
              {
                title: t('itsm.ticket.action'),
                key: 'actions',
                render: (_value: unknown, item: EntryItem) => (
                  <Button type="link" size="small" danger onClick={() => {
                    void api.deleteDictionaryItem(current.id, item.id).then(() => openItems(current));
                  }}>{t('itsm.common.delete')}</Button>
                ),
              },
            ]}
          />
        </div>
      ) : null}
    </div>
  );
}
