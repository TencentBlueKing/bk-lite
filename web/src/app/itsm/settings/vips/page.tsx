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

interface VipItem {
  id: number;
  username: string;
}

export default function Page() {
  const { t } = useTranslation();
  const api = useItsmApi();
  const [open,setOpen] = useState(false);
  const [keyword,setKeyword] = useState('');
  const [saving,setSaving] = useState(false);
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
      <div className="rounded-lg border border-[var(--color-border)] bg-[var(--color-bg)] p-4">
        <ItsmListToolbar search={{value:keyword,onChange:setKeyword,placeholder:'搜索用户'}} actions={<ItsmCreateButton onClick={() => setOpen(true)} />} />
        <CustomTable queryKey={keyword}
          rowKey="id"
          dataSource={items.filter(item => `${item.username}`.toLowerCase().includes(keyword.trim().toLowerCase()))}
          locale={{ emptyText: t('itsm.admin.emptyVip') }}
          columns={[
            { title: t('itsm.admin.username'), dataIndex: 'username', key: 'username' },
            { fixed: 'right' as const, width: 120,
              title: t('itsm.ticket.action'),
              key: 'actions',
              render: (_value: unknown, item: VipItem) => <ItsmRowActions items={[{key: 'action-0', label: t('itsm.common.delete'), kind: 'delete' as const, danger: true, confirm: {title: t('itsm.admin.deleteUser'), content: undefined }, onClick: () => { void api.deleteResource('vips', item.id).then(load); }}]} />,
            },
          ]}
        />
      </div>
      <OperateModal title="新建" open={open} onCancel={() => setOpen(false)} confirmLoading={saving} onOk={async () => {
        if (!username[0]) { message.warning('请选择用户'); return; }
        setSaving(true);
        try { await api.createResource('vips',{username:username[0]}); setOpen(false);setUsername([]);await load(); } catch(error) { message.error(error instanceof Error ? error.message : '保存失败'); } finally { setSaving(false); }
      }}><div className="flex flex-col gap-4"><FieldRow label={t('itsm.admin.username')}><UserSelector multiple={false} value={username} onChange={setUsername} /></FieldRow></div></OperateModal>
    </div>
  );
}
