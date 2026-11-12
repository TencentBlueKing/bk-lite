'use client';

import { Button, Input, Popconfirm, Select, message } from 'antd';
import { useCallback, useEffect, useState } from 'react';
import OperateModal from '@/components/operate-modal';
import CustomTable from '@/components/custom-table';
import { useItsmApi } from '../../api/useItsmApi';
import { FieldRow } from '../../components/field-row';
import { useTranslation } from '@/utils/i18n';

interface SourceItem {
  id: number;
  name: string;
  kind: string;
  config: { url?: string; table_key?: string };
}

export default function Page() {
  const { t } = useTranslation();
  const api = useItsmApi();
  const [items, setItems] = useState<SourceItem[]>([]);
  const [open, setOpen] = useState(false);
  const [name, setName] = useState('');
  const [kind, setKind] = useState<'http' | 'table'>('http');
  const [target, setTarget] = useState('');

  const load = useCallback(async () => {
    const data = await api.listResources('sources') as { items?: SourceItem[] };
    setItems(data.items || []);
  }, [api.listResources]);

  useEffect(() => {
    if (!api.ready) {
      return;
    }
    void load().catch((error: unknown) => message.error(error instanceof Error ? error.message : t('itsm.ticket.loadFailed')));
  }, [api.ready, load]);

  const save = async () => {
    if (!name.trim() || !target.trim()) {
      message.warning(kind === 'http' ? t('itsm.admin.needSource') : t('itsm.admin.needTableKey'));
      return;
    }
    await api.createResource('sources', {
      name: name.trim(),
      kind,
      config: kind === 'http' ? { url: target.trim() } : { table_key: target.trim() },
    });
    setOpen(false);
    setName('');
    setTarget('');
    message.success(t('itsm.portal.created'));
    await load();
  };

  return (
    <div className="flex flex-col gap-4">
      <div className="flex items-center justify-between rounded-lg border border-[var(--color-border)] bg-[var(--color-bg)] px-4 py-3">
        <div className="text-sm font-medium text-[var(--color-text-1)]">{t('itsm.admin.sources')}</div>
        <Button type="primary" onClick={() => setOpen(true)}>{t('itsm.common.create')}</Button>
      </div>
      <div className="rounded-lg border border-[var(--color-border)] bg-[var(--color-bg)] p-4">
        <CustomTable
          rowKey="id"
          dataSource={items}
          pagination={false}
          locale={{ emptyText: t('itsm.admin.emptySources') }}
          columns={[
            { title: t('itsm.portal.name'), dataIndex: 'name', key: 'name' },
            { title: t('itsm.rule.kind'), dataIndex: 'kind', key: 'kind', render: (value: string) => value === 'table' ? t('itsm.admin.tableSource') : 'HTTP' },
            { title: t('itsm.admin.target'), key: 'target', render: (_value: unknown, item: SourceItem) => item.config?.url || item.config?.table_key || '—' },
            {
              title: t('itsm.ticket.action'),
              key: 'actions',
              render: (_value: unknown, item: SourceItem) => (
                <Popconfirm title={t('itsm.admin.deleteSource')} onConfirm={() => { void api.deleteResource('sources', item.id).then(load); }}>
                  <Button type="link" size="small" danger>{t('itsm.common.delete')}</Button>
                </Popconfirm>
              ),
            },
          ]}
        />
      </div>
      <OperateModal title={t('itsm.admin.newSource')} open={open} onCancel={() => setOpen(false)} onOk={() => { void save(); }}>
        <div className="flex flex-col gap-3">
          <FieldRow label={t('itsm.portal.name')}>
            <Input placeholder={t('itsm.portal.name')} value={name} onChange={(event) => setName(event.target.value)} />
          </FieldRow>
          <FieldRow label={t('itsm.rule.kind')}>
            <Select className="w-full" value={kind} options={[{ value: 'http', label: t('itsm.admin.http') }, { value: 'table', label: t('itsm.admin.tableSource') }]} onChange={setKind} />
          </FieldRow>
          <FieldRow label={kind === 'http' ? t('itsm.admin.sourceUrl') : t('itsm.admin.tableKey')}>
            <Input placeholder={kind === 'http' ? t('itsm.admin.sourceUrl') : t('itsm.admin.tableKey')} value={target} onChange={(event) => setTarget(event.target.value)} />
          </FieldRow>
        </div>
      </OperateModal>
    </div>
  );
}
