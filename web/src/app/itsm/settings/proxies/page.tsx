'use client';

import { Button, Popconfirm, message } from 'antd';
import { useCallback, useEffect, useState } from 'react';
import CustomTable from '@/components/custom-table';
import { useItsmApi } from '../../api/useItsmApi';
import { useTranslation } from '@/utils/i18n';
import { UserSelector } from '../../components/user-selector';

interface ProxyItem {
  id: number;
  principal: string;
  agent: string;
  is_enabled: boolean;
}

export default function Page() {
  const { t } = useTranslation();
  const api = useItsmApi();
  const [items, setItems] = useState<ProxyItem[]>([]);
  const [principal, setPrincipal] = useState<string[]>([]);
  const [agent, setAgent] = useState<string[]>([]);

  const load = useCallback(async () => {
    const data = await api.listResources('proxies') as { items?: ProxyItem[] };
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
      <div className="flex flex-wrap items-center justify-between gap-3 rounded-lg border border-[var(--color-border)] bg-[var(--color-bg)] px-4 py-3">
        <div className="text-base font-semibold leading-tight text-[var(--color-text-1)]">{t('itsm.admin.proxy')}</div>
        <div className="flex gap-2">
          <div className="w-40"><UserSelector multiple={false} placeholder={t('itsm.admin.principal')} value={principal} onChange={setPrincipal} /></div>
          <div className="w-40"><UserSelector multiple={false} placeholder={t('itsm.admin.agent')} value={agent} onChange={setAgent} /></div>
          <Button type="primary" onClick={() => {
            if (!principal[0] || !agent[0]) {
              message.warning(t('itsm.admin.needBoth'));
              return;
            }
            void api.createResource('proxies', { principal: principal[0], agent: agent[0], is_enabled: true }).then(load);
          }}>{t('itsm.common.create')}</Button>
        </div>
      </div>
      <div className="rounded-lg border border-[var(--color-border)] bg-[var(--color-bg)] p-4">
        <CustomTable
          rowKey="id"
          dataSource={items}
          pagination={false}
          locale={{ emptyText: t('itsm.admin.emptyProxy') }}
          columns={[
            { title: t('itsm.admin.principal'), dataIndex: 'principal', key: 'principal' },
            { title: t('itsm.admin.agent'), dataIndex: 'agent', key: 'agent' },
            { title: t('itsm.admin.state'), key: 'enabled', render: (_value: unknown, item: ProxyItem) => (item.is_enabled ? t('itsm.admin.enable') : t('itsm.admin.disable')) },
            {
              title: t('itsm.ticket.action'),
              key: 'actions',
              render: (_value: unknown, item: ProxyItem) => (
                <span className="inline-flex gap-2">
                  <Button type="link" size="small" onClick={() => {
                    void api.updateResource('proxies', item.id, { is_enabled: !item.is_enabled }).then(load);
                  }}>{item.is_enabled ? t('itsm.admin.disable') : t('itsm.admin.enable')}</Button>
                  <Popconfirm title={t('itsm.admin.deleteProxy')} onConfirm={() => { void api.deleteResource('proxies', item.id).then(load); }}>
                    <Button type="link" size="small" danger>{t('itsm.common.delete')}</Button>
                  </Popconfirm>
                </span>
              ),
            },
          ]}
        />
      </div>
    </div>
  );
}
