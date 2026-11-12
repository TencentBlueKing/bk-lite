'use client';

import { Button, Input, message } from 'antd';
import Link from 'next/link';
import { useRouter } from 'next/navigation';
import { useCallback, useEffect, useState } from 'react';
import CustomTable from '@/components/custom-table';
import { useTranslation } from '@/utils/i18n';
import { useItsmApi } from '../api/useItsmApi';
import type { NamedItem } from '../types';

export default function FormListPage() {
  const { t } = useTranslation();
  const api = useItsmApi();
  const router = useRouter();
  const [items, setItems] = useState<NamedItem[]>([]);
  const [name, setName] = useState('');
  const [keyword, setKeyword] = useState('');

  const load = useCallback(async () => {
    const data = await api.listForms() as { items?: NamedItem[] };
    setItems(data.items || []);
  }, [api.listForms]);

  useEffect(() => {
    if (!api.ready) {
      return;
    }
    void load().catch((error: unknown) => message.error(error instanceof Error ? error.message : t('itsm.ticket.loadFailed')));
  }, [api.ready, load]);

  const create = async () => {
    if (!name.trim()) {
      message.warning(t('itsm.admin.needFormName'));
      return;
    }
    const created = await api.createForm({ name: name.trim(), key: `form_${Date.now()}` }) as { id: number };
    router.push(`/itsm/form/designer/${created.id}`);
  };

  return (
    <div className="flex flex-col gap-4">
      <div className="flex flex-wrap items-center justify-between gap-4 rounded-lg border border-[var(--color-border)] bg-[var(--color-bg)] p-4">
        <div className="flex flex-col gap-1">
          <div className="text-base font-semibold leading-tight text-[var(--color-text-1)]">{t('itsm.admin.form')}</div>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          <Input
            className="w-48"
            placeholder={t('itsm.admin.formName')}
            value={name}
            onChange={(event) => setName(event.target.value)}
          />
          <Input className="w-48" placeholder={t('itsm.admin.searchName')} value={keyword} onChange={(event) => setKeyword(event.target.value)} allowClear />
          <Button type="primary" onClick={() => { void create(); }}>{t('itsm.admin.newForm')}</Button>
        </div>
      </div>
      <div className="rounded-lg border border-[var(--color-border)] bg-[var(--color-bg)] p-4">
        <CustomTable
          rowKey="id"
          dataSource={items.filter((item) => !keyword.trim() || `${item.name} ${item.key}`.includes(keyword.trim()))}
          locale={{ emptyText: t('itsm.admin.emptyForm') }}
          columns={[
            { title: t('itsm.portal.name'), dataIndex: 'name', key: 'name' },
            { title: t('itsm.admin.key'), dataIndex: 'key', key: 'key' },
            {
              title: t('itsm.ticket.action'),
              key: 'action',
              render: (_value, record: NamedItem) => (
                <Link href={`/itsm/form/designer/${record.id}`} className="text-[var(--color-primary)]">
                  {t('itsm.admin.designForm')}
                </Link>
              ),
            },
          ]}
        />
      </div>
    </div>
  );
}
