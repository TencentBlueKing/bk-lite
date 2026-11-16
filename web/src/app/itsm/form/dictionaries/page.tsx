'use client';

import { Alert, Button, Input, InputNumber, Popconfirm, Switch, Tag, Upload, message } from 'antd';
import { useCallback, useEffect, useRef, useState } from 'react';
import OperateModal from '@/components/operate-modal';
import CustomTable from '@/app/itsm/components/itsm-list-table';
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
  order?: number;
  is_enabled?: boolean;
  parent_id?: number | null;
}

export default function DictionariesPage() {
  const { t } = useTranslation();
  const api = useItsmApi();
  const [items, setItems] = useState<DictionaryItem[]>([]);
  const [name, setName] = useState('');
  const [keyword, setKeyword] = useState('');
  const [dictKey, setDictKey] = useState('');
  const [current, setCurrent] = useState<DictionaryItem | null>(null);
  const [entries, setEntries] = useState<EntryItem[]>([]);
  const [entryKey, setEntryKey] = useState('');
  const [entryLabel, setEntryLabel] = useState('');
  const [createOpen, setCreateOpen] = useState(false);
  const [editing, setEditing] = useState<DictionaryItem | null>(null);

  const [canEdit, setCanEdit] = useState(false);
  const [canImport, setCanImport] = useState(false);
  const [canEditEntries, setCanEditEntries] = useState(false);
  const [entryOpen, setEntryOpen] = useState(false);
  const [editingEntry, setEditingEntry] = useState<EntryItem | null>(null);
  const [order, setOrder] = useState(0);
  const [enabled, setEnabled] = useState(true);
  const [loading, setLoading] = useState(false);
  const [busy, setBusy] = useState(false);
  const [importing, setImporting] = useState(false);
  const [error, setError] = useState('');
  const sequence = useRef(0);
  const showError = (error: unknown) => message.error(error instanceof Error ? error.message : '操作失败，请重试');
  const editEntry = (entry: EntryItem | null) => {
    setEditingEntry(entry); setEntryKey(entry?.key || ''); setEntryLabel(entry?.label || '');
    setOrder(entry?.order || 0); setEnabled(entry?.is_enabled ?? true); setEntryOpen(true);
  };
  const saveEntry = async () => {
    if (!current || !entryKey.trim() || !entryLabel.trim()) { message.warning('请填写名称和标识'); return; }
    setBusy(true);
    try {
      await api.createDictionaryItem(current.id, { id: editingEntry?.id, key: entryKey.trim(), label: entryLabel.trim(), order, is_enabled: enabled });
      setEntryOpen(false); await openItems(current); message.success('字典项已保存');
    } catch (error) { showError(error); } finally { setBusy(false); }
  };

  const load = useCallback(async () => {
    const data = await api.listDictionaries() as { items?: DictionaryItem[]; can_edit?: boolean; can_add?: boolean };
    setItems(data.items || []);
    setCanEdit(Boolean(data.can_edit)); setCanImport(Boolean(data.can_add));
  }, [api.listDictionaries]);

  useEffect(() => {
    if (!api.ready) {
      return;
    }
    void load().catch((error: unknown) => message.error(error instanceof Error ? error.message : t('itsm.ticket.loadFailed')));
  }, [api.ready, load]);

  const openItems = async (item: DictionaryItem) => {
    const seq = ++sequence.current;
    setCurrent(item); setLoading(true); setEntries([]); setCanEditEntries(false); setError('');
    try {
      const data = await api.listDictionaryItems(item.id) as { items?: EntryItem[]; can_edit?: boolean };
      if (seq !== sequence.current) return;
      setEntries(data.items || []); setCanEditEntries(Boolean(data.can_edit));
    } catch (error) {
      if (seq === sequence.current) setError(error instanceof Error ? error.message : '加载失败');
    } finally { if (seq === sequence.current) setLoading(false); }
  };

  const exportFile = async () => {
    const rows = await api.exportDictionaries();
    const blob = new Blob([JSON.stringify(rows, null, 2)], { type: 'application/json' });
    const link = document.createElement('a');
    link.href = URL.createObjectURL(blob);
    link.download = 'dictionaries.json';
    link.click();
    URL.revokeObjectURL(link.href);
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
      <div className="rounded-lg border border-[var(--color-border)] bg-[var(--color-bg)] p-4">
        <div className="mb-4 flex flex-wrap items-center justify-between gap-3">
          <div className="flex flex-wrap items-center gap-2">
            {canEdit && <Button type="primary" onClick={() => { setEditing(null); setName(''); setDictKey(''); setCreateOpen(true); }}>{t('itsm.admin.newDictionary')}</Button>}
            <Button onClick={() => { void exportFile().catch(showError); }}>{t('itsm.admin.exportAll')}</Button>
            {canImport && <Upload accept=".json,application/json" showUploadList={false} beforeUpload={async (file) => {
              if (file.size > 10 * 1024 * 1024) { message.error('文件不能超过 10 MB'); return false; }
              setImporting(true);
              try {
                const rows: unknown = JSON.parse(await file.text());
                if (!Array.isArray(rows)) throw new Error('请选择导出的字典 JSON 文件');
                const result = await api.importDictionaries(rows) as { created: number };
                await load(); message.success(`已导入 ${result.created} 个字典`);
              } catch (error) { showError(error); } finally { setImporting(false); }
              return false;
            }}><Button loading={importing}>导入</Button></Upload>}

          </div>
          <Input aria-label="搜索数据字典" className="!w-64" placeholder="搜索名称或标识" value={keyword} onChange={event => setKeyword(event.target.value)} allowClear />
        </div>
        <CustomTable
          rowKey="id"
          dataSource={items.filter(item => `${item.name} ${item.key}`.toLowerCase().includes(keyword.trim().toLowerCase()))}
          locale={{ emptyText: t('itsm.admin.emptyDictionary') }}
          columns={[
            { title: t('itsm.portal.name'), dataIndex: 'name', key: 'name' },
            { title: t('itsm.admin.key'), dataIndex: 'key', key: 'key' },
            {
              title: t('itsm.ticket.action'),
              key: 'actions',
              render: (_value: unknown, item: DictionaryItem) => (
                <span className="inline-flex gap-2">
                  {canEdit && <Button type="link" size="small" onClick={() => { setEditing(item); setName(item.name); setDictKey(item.key); setCreateOpen(true); }}>{t('itsm.common.edit')}</Button>}
                  <Button type="link" size="small" onClick={() => { void openItems(item); }}>{t('itsm.admin.items')}</Button>
                </span>
              ),
            },
          ]}
        />
      </div>
      <OperateModal title={editing ? t('itsm.admin.editDictionary') : t('itsm.admin.newDictionaryTitle')} open={createOpen} onCancel={() => setCreateOpen(false)} onOk={() => { void create().catch(showError); }}>
        <div className="flex flex-col gap-3 text-sm">
          <FieldRow label={t('itsm.admin.dictName')}>
            <Input value={name} onChange={(event) => setName(event.target.value)} />
          </FieldRow>
          <FieldRow label={t('itsm.admin.dictKey')}>
            <Input value={dictKey} disabled={Boolean(editing)} onChange={(event) => setDictKey(event.target.value)} />
          </FieldRow>
        </div>
      </OperateModal>
      <OperateModal title={`字典项 · ${current?.name || ''}`} open={Boolean(current)} width={900} footer={null}
        onCancel={() => { sequence.current++; setCurrent(null); setEntries([]); setEntryOpen(false); }}>
        {canEditEntries && <Button type="primary" className="mb-4" onClick={() => editEntry(null)}>新增字典项</Button>}
        {error ? <Alert type="error" message={error} action={<Button onClick={() => { if (current) void openItems(current); }}>重试</Button>} /> :
          <CustomTable rowKey="id" loading={loading} dataSource={entries} scroll={{ y: '45vh' }} columns={[
            { title: '名称', dataIndex: 'label', key: 'label' },
            { title: '标识', dataIndex: 'key', key: 'key' },
            { title: '上级字典项', key: 'parent', render: (_: unknown, item: EntryItem) => entries.find(parent => parent.id === item.parent_id)?.label || '—' },
            { title: '排序', dataIndex: 'order', key: 'order' },
            { title: '状态', key: 'status', render: (_: unknown, item: EntryItem) => <Tag color={item.is_enabled === false ? 'default' : 'green'}>{item.is_enabled === false ? '已停用' : '已启用'}</Tag> },
            ...(canEditEntries ? [{ title: '操作', key: 'actions', render: (_: unknown, item: EntryItem) => <span className="inline-flex gap-2">
              <Button type="link" size="small" onClick={() => editEntry(item)}>编辑</Button>
              <Popconfirm title="确认删除该字典项？" onConfirm={async () => {
                if (!current) return;
                try { await api.deleteDictionaryItem(current.id, item.id); await openItems(current); } catch (error) { showError(error); }
              }}><Button type="link" size="small" danger disabled={entries.some(child => child.parent_id === item.id)}>删除</Button></Popconfirm>
            </span> }] : []),
          ]} />}
      </OperateModal>
      <OperateModal title={editingEntry ? '编辑字典项' : '新增字典项'} open={entryOpen} confirmLoading={busy} onCancel={() => setEntryOpen(false)} onOk={() => void saveEntry()}>
        <div className="flex flex-col gap-4">
          <FieldRow label="名称"><Input aria-label="字典项名称" maxLength={128} value={entryLabel} onChange={event => setEntryLabel(event.target.value)} /></FieldRow>
          <FieldRow label="标识"><Input aria-label="字典项标识" maxLength={64} disabled={Boolean(editingEntry)} value={entryKey} onChange={event => setEntryKey(event.target.value)} /></FieldRow>
          {editingEntry && <span className="text-xs text-[var(--color-text-3)]">标识用于表单存储，创建后不可修改。</span>}
          <FieldRow label="排序"><InputNumber aria-label="排序" min={0} max={2147483647} precision={0} value={order} onChange={value => setOrder(value ?? 0)} /></FieldRow>
          <FieldRow label="启用"><Switch aria-label="启用" checked={enabled} onChange={setEnabled} /></FieldRow>
        </div>
      </OperateModal>
    </div>
  );
}
