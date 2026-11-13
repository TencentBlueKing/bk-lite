'use client';

import { Button, Input, Popconfirm, Tag, message } from 'antd';
import { useCallback, useEffect, useState } from 'react';
import OperateModal from '@/components/operate-modal';
import CustomTable from '@/app/itsm/components/itsm-list-table';
import { useItsmApi } from '../../api/useItsmApi';
import { useTranslation } from '@/utils/i18n';
import { UserSelector } from '../../components/user-selector';
import { FieldRow } from '../../components/field-row';

interface HandlerGroupItem {
  id: number;
  name: string;
  members: string[];
  leaders: string[];
}

export default function HandlerGroupsPage() {
  const { t } = useTranslation();
  const api = useItsmApi();
  const [items, setItems] = useState<HandlerGroupItem[]>([]);
  const [keyword, setKeyword] = useState('');
  const [open, setOpen] = useState(false);
  const [editing, setEditing] = useState<HandlerGroupItem | null>(null);
  const [name, setName] = useState('');
  const [members, setMembers] = useState<string[]>([]);

  const load = useCallback(async () => {
    const data = await api.listHandlerGroups() as { items?: HandlerGroupItem[] };
    setItems(data.items || []);
  }, [api.listHandlerGroups]);

  useEffect(() => {
    if (!api.ready) {
      return;
    }
    void load().catch((error: unknown) => message.error(error instanceof Error ? error.message : t('itsm.ticket.loadFailed')));
  }, [api.ready, load]);

  const start = (item?: HandlerGroupItem) => {
    setEditing(item || null);
    setName(item?.name || '');
    setMembers(item?.members || []);
    setOpen(true);
  };

  const save = async () => {
    if (!name.trim()) {
      message.warning(t('itsm.admin.needGroup'));
      return;
    }
    await api.createHandlerGroup({ id: editing?.id, name: name.trim(), members, leaders: members.slice(0, 1) });
    setOpen(false);
    message.success(editing ? t('itsm.portal.saved') : t('itsm.portal.created'));
    await load();
  };

  const shown = items.filter((item) => !keyword.trim() || item.name.includes(keyword.trim()));

  return (
    <div className="flex flex-col gap-4">
      <div className="flex items-center justify-between rounded-lg border border-[var(--color-border)] bg-[var(--color-bg)] px-4 py-3">
        <div className="text-sm font-medium text-[var(--color-text-1)]">{t('itsm.admin.groups')}</div>
        <div className="flex gap-2">
          <Input className="w-48" placeholder={t('itsm.admin.searchGroup')} value={keyword} onChange={(event) => setKeyword(event.target.value)} allowClear />
          <Button type="primary" onClick={() => start()}>{t('itsm.common.create')}</Button>
        </div>
      </div>
      <div className="rounded-lg border border-[var(--color-border)] bg-[var(--color-bg)] p-4">
        <CustomTable
          rowKey="id"
          dataSource={shown}
          locale={{ emptyText: t('itsm.admin.emptyGroup') }}
          columns={[
            { title: t('itsm.portal.name'), dataIndex: 'name', key: 'name' },
            { title: t('itsm.admin.leader'), dataIndex: 'leaders', key: 'leaders', render: (leaders: string[]) => leaders?.length ? leaders.map((user) => <Tag key={user}>{user}</Tag>) : '—' },
            { title: t('itsm.admin.members'), dataIndex: 'members', key: 'members', render: (value: string[]) => value?.join('、') || '—' },
            {
              title: t('itsm.ticket.action'),
              key: 'actions',
              render: (_value: unknown, item: HandlerGroupItem) => (
                <span className="inline-flex gap-2">
                  <Button type="link" size="small" onClick={() => start(item)}>{t('itsm.common.edit')}</Button>
                  <Popconfirm title={t('itsm.admin.deleteGroup')} onConfirm={() => { void api.deleteHandlerGroup(item.id).then(load); }}>
                    <Button type="link" size="small" danger>{t('itsm.common.delete')}</Button>
                  </Popconfirm>
                </span>
              ),
            },
          ]}
        />
      </div>
      <OperateModal title={editing ? t('itsm.admin.editGroup') : t('itsm.admin.newGroup')} open={open} onCancel={() => setOpen(false)} onOk={() => { void save(); }}>
        <div className="flex flex-col gap-3">
          <FieldRow label={t('itsm.portal.name')}>
            <Input placeholder={t('itsm.admin.groupName')} value={name} onChange={(event) => setName(event.target.value)} />
          </FieldRow>
          <FieldRow label={t('itsm.admin.members')}>
            <UserSelector value={members} onChange={setMembers} />
          </FieldRow>
        </div>
      </OperateModal>
    </div>
  );
}
