'use client';

import { ItsmRowActions, ItsmListToolbar, ItsmCreateButton } from '@/app/itsm/components/list-controls';

import { message } from 'antd';
import OperateModal from '@/components/operate-modal';
import { FieldRow } from '../../components/field-row';
import { useCallback, useEffect, useState } from 'react';
import CustomTable from '@/app/itsm/components/itsm-list-table';
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
  const [open,setOpen] = useState(false);
  const [keyword,setKeyword] = useState('');
  const [saving,setSaving] = useState(false);
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
      <div className="rounded-lg border border-[var(--color-border)] bg-[var(--color-bg)] p-4">
        <ItsmListToolbar search={{value:keyword,onChange:setKeyword,placeholder:'搜索用户'}} actions={<ItsmCreateButton onClick={() => setOpen(true)} />} />
        <CustomTable queryKey={keyword}
          rowKey="id"
          dataSource={items.filter(item => `${item.principal} ${item.agent}`.toLowerCase().includes(keyword.trim().toLowerCase()))}
          locale={{ emptyText: t('itsm.admin.emptyProxy') }}
          columns={[
            { title: t('itsm.admin.principal'), dataIndex: 'principal', key: 'principal' },
            { title: t('itsm.admin.agent'), dataIndex: 'agent', key: 'agent' },
            { title: t('itsm.admin.state'), key: 'enabled', render: (_value: unknown, item: ProxyItem) => (item.is_enabled ? t('itsm.admin.enable') : t('itsm.admin.disable')) },
            { fixed: 'right' as const, width: 120,
              title: t('itsm.ticket.action'),
              key: 'actions',
              render: (_value: unknown, item: ProxyItem) => <ItsmRowActions items={[{key: 'action-0', label: item.is_enabled ? t('itsm.admin.disable') : t('itsm.admin.enable'), kind: 'publish' as const, onClick: () => {
                void api.updateResource('proxies', item.id, { is_enabled: !item.is_enabled }).then(load);
              }},
              {key: 'action-1', label: t('itsm.common.delete'), kind: 'delete' as const, danger: true, confirm: {title: t('itsm.admin.deleteProxy'), content: undefined }, onClick: () => { void api.deleteResource('proxies', item.id).then(load); }}]} />,
            },
          ]}
        />
      </div>
      <OperateModal title="新建" open={open} onCancel={() => setOpen(false)} confirmLoading={saving} onOk={async () => {
        if (!principal[0] || !agent[0]) { message.warning(t('itsm.admin.needBoth')); return; }
        setSaving(true);
        try { await api.createResource('proxies',{principal:principal[0],agent:agent[0],is_enabled:true}); setOpen(false);setPrincipal([]);setAgent([]);await load(); } catch(error) { message.error(error instanceof Error ? error.message : '保存失败'); } finally { setSaving(false); }
      }}><div className="flex flex-col gap-4"><FieldRow label={t('itsm.admin.principal')}><UserSelector multiple={false} value={principal} onChange={setPrincipal} /></FieldRow><FieldRow label={t('itsm.admin.agent')}><UserSelector multiple={false} value={agent} onChange={setAgent} /></FieldRow></div></OperateModal>
    </div>
  );
}
