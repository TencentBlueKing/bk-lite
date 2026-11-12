'use client';

import { Button, Popconfirm, message } from 'antd';
import { useCallback, useEffect, useState } from 'react';
import CustomTable from '@/components/custom-table';
import { useItsmApi } from '../../api/useItsmApi';
import { useTranslation } from '@/utils/i18n';
import { UserSelector } from '../../components/user-selector';

interface VipItem {
  id: number;
  username: string;
}

export default function Page() {
  const { t } = useTranslation();
  const api = useItsmApi();
  const [items, setItems] = useState<VipItem[]>([]);
  const [username, setUsername] = useState<string[]>([]);

  const load = useCallback(async () => {
    const data = await api.listResources('vips') as { items?: VipItem[] };
    setItems(data.items || []);
  }, [api.listResources]);

  useEffect(() => {
    if (!api.ready) {
      return;
    }
    void load().catch((error: unknown) => message.error(error instanceof Error ? error.message : t('itsm.ticket.loadFailed')));
  }, [api.ready, load]);

  return (
    <div className="flex flex-col gap-4">
      <div className="flex items-center justify-between rounded-lg border border-[var(--color-border)] bg-[var(--color-bg)] px-4 py-3">
        <div className="text-base font-semibold leading-tight text-[var(--color-text-1)]">{t('itsm.admin.vip')}</div>
        <div className="flex gap-2">
          <div className="w-56">
            <UserSelector multiple={false} value={username} onChange={setUsername} />
          </div>
          <Button type="primary" onClick={() => {
            if (!username[0]) {
              return;
            }
            void api.createResource('vips', { username: username[0] }).then(() => {
              setUsername([]);
              return load();
            });
          }}>{t('itsm.admin.addUser')}</Button>
        </div>
      </div>
      <div className="rounded-lg border border-[var(--color-border)] bg-[var(--color-bg)] p-4">
        <CustomTable
          rowKey="id"
          dataSource={items}
          pagination={false}
          locale={{ emptyText: t('itsm.admin.emptyVip') }}
          columns={[
            { title: t('itsm.admin.username'), dataIndex: 'username', key: 'username' },
            {
              title: t('itsm.ticket.action'),
              key: 'actions',
              render: (_value: unknown, item: VipItem) => (
                <Popconfirm title={t('itsm.admin.deleteUser')} onConfirm={() => { void api.deleteResource('vips', item.id).then(load); }}>
                  <Button type="link" size="small" danger>{t('itsm.common.delete')}</Button>
                </Popconfirm>
              ),
            },
          ]}
        />
      </div>
    </div>
  );
}
