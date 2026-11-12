'use client';

import { Button, Input, message } from 'antd';
import { useCallback, useEffect, useMemo, useState } from 'react';
import OperateModal from '@/components/operate-modal';
import CustomTable from '@/components/custom-table';
import { useItsmApi } from '../../api/useItsmApi';
import { FieldRow } from '../../components/field-row';
import { useTranslation } from '@/utils/i18n';

interface TableItem {
  id: number;
  name: string;
  key: string;
}

interface RowItem {
  id: number;
  data: Record<string, unknown>;
}

export default function DataTablesPage() {
  const { t } = useTranslation();
  const api = useItsmApi();
  const [items, setItems] = useState<TableItem[]>([]);
  const [name, setName] = useState('');
  const [tableKey, setTableKey] = useState('');
  const [rows, setRows] = useState<RowItem[]>([]);
  const [active, setActive] = useState<TableItem | null>(null);
  const [open, setOpen] = useState(false);

  const load = useCallback(async () => {
    const data = await api.listDataTables() as { items?: TableItem[] };
    setItems(data.items || []);
  }, [api.listDataTables]);

  useEffect(() => {
    if (!api.ready) {
      return;
    }
    void load().catch((error: unknown) => message.error(error instanceof Error ? error.message : t('itsm.ticket.loadFailed')));
  }, [api.ready, load]);

  const openRows = async (item: TableItem) => {
    const data = await api.listDataRows(item.id) as { items?: RowItem[] };
    setActive(item);
    setRows(data.items || []);
  };

  const download = async (id: number) => {
    const data = await api.exportDataTable(id) as { filename: string; content_base64: string };
    const binary = window.atob(data.content_base64);
    const bytes = new Uint8Array(binary.length);
    for (let index = 0; index < binary.length; index += 1) {
      bytes[index] = binary.charCodeAt(index);
    }
    const url = URL.createObjectURL(new Blob([bytes]));
    const link = document.createElement('a');
    link.href = url;
    link.download = data.filename;
    link.click();
    URL.revokeObjectURL(url);
  };

  const upload = async (item: TableItem, file: File) => {
    const content = await new Promise<string>((resolve, reject) => {
      const reader = new FileReader();
      reader.onload = () => resolve(String(reader.result || '').split(',')[1] || '');
      reader.onerror = () => reject(reader.error);
      reader.readAsDataURL(file);
    });
    await api.importDataTable(item.id, content);
    await openRows(item);
    message.success(t('itsm.admin.importedRows'));
  };

  const create = async () => {
    if (!name.trim() || !tableKey.trim()) {
      message.warning(t('itsm.admin.needTable'));
      return;
    }
    await api.createDataTable({ name: name.trim(), key: tableKey.trim(), fields: [{ key: 'name', type: 'string' }] });
    setName('');
    setTableKey('');
    setOpen(false);
    message.success(t('itsm.portal.created'));
    await load();
  };

  const rowColumns = useMemo(() => {
    const keys = Array.from(new Set(rows.flatMap((row) => Object.keys(row.data || {}))));
    const dataColumns = (keys.length ? keys : ['name']).map((key) => ({
      title: key,
      key,
      dataIndex: key,
      render: (_value: unknown, row: RowItem) => String(row.data?.[key] ?? ''),
    }));
    return [
      ...dataColumns,
      {
        title: t('itsm.ticket.action'),
        key: 'actions',
        render: (_value: unknown, row: RowItem) => (
          <Button
            type="link"
            size="small"
            danger
            onClick={() => {
              if (!active) {
                return;
              }
              void api.deleteDataRows(active.id, [row.id]).then(() => openRows(active));
            }}
          >
            {t('itsm.common.delete')}
          </Button>
        ),
      },
    ];
  }, [rows, active, api, t]);

  return (
    <div className="flex flex-col gap-4">
      <div className="flex items-center justify-between rounded-lg border border-[var(--color-border)] bg-[var(--color-bg)] px-4 py-3">
        <div className="text-sm font-medium text-[var(--color-text-1)]">{t('itsm.admin.tables')}</div>
        <Button type="primary" onClick={() => setOpen(true)}>{t('itsm.common.create')}</Button>
      </div>
      <div className="rounded-lg border border-[var(--color-border)] bg-[var(--color-bg)] p-4">
        <CustomTable
          rowKey="id"
          dataSource={items}
          pagination={false}
          locale={{ emptyText: t('itsm.admin.emptyTables') }}
          columns={[
            { title: t('itsm.portal.name'), dataIndex: 'name', key: 'name' },
            { title: t('itsm.admin.key'), dataIndex: 'key', key: 'key' },
            {
              title: t('itsm.ticket.action'),
              key: 'actions',
              render: (_value: unknown, item: TableItem) => (
                <span className="inline-flex items-center gap-2">
                  <Button type="link" size="small" onClick={() => { void openRows(item); }}>{t('itsm.admin.data')}</Button>
                  <Button type="link" size="small" onClick={() => { void download(item.id); }}>{t('itsm.admin.export')}</Button>
                  <label className="cursor-pointer text-[var(--color-primary)]">
                    {t('itsm.admin.import')}
                    <input
                      className="hidden"
                      type="file"
                      accept=".xlsx"
                      onChange={(event) => {
                        const file = event.target.files?.[0];
                        if (file) {
                          void upload(item, file).catch((error: unknown) => message.error(error instanceof Error ? error.message : t('itsm.admin.importFailed')));
                        }
                        event.target.value = '';
                      }}
                    />
                  </label>
                </span>
              ),
            },
          ]}
        />
      </div>
      {active ? (
        <div className="rounded-lg border border-[var(--color-border)] bg-[var(--color-bg)] p-4">
          <div className="mb-3 text-sm font-medium text-[var(--color-text-1)]">{t('itsm.admin.tableData', undefined, { name: active.name })}</div>
          <CustomTable
            rowKey="id"
            dataSource={rows}
            pagination={false}
            locale={{ emptyText: t('itsm.admin.emptyRows') }}
            columns={rowColumns}
          />
        </div>
      ) : null}
      <OperateModal title={t('itsm.admin.newTable')} open={open} onCancel={() => setOpen(false)} onOk={() => { void create(); }}>
        <div className="flex flex-col gap-3">
          <FieldRow label={t('itsm.portal.name')}>
            <Input placeholder={t('itsm.portal.name')} value={name} onChange={(event) => setName(event.target.value)} />
          </FieldRow>
          <FieldRow label={t('itsm.admin.key')}>
            <Input placeholder={t('itsm.admin.key')} value={tableKey} onChange={(event) => setTableKey(event.target.value)} />
          </FieldRow>
        </div>
      </OperateModal>
    </div>
  );
}
