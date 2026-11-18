'use client';

import { ItsmListEntry } from '@/app/itsm/components/list-entry';

import { ItsmRowActions, ItsmListToolbar, ItsmCreateButton } from '@/app/itsm/components/list-controls';

import { Input, Tag, message } from 'antd';
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
      <div className="rounded-lg border border-[var(--color-border)] bg-[var(--color-bg)] p-4">
        <ItsmListToolbar search={{ value: keyword, onChange: setKeyword, placeholder: t('itsm.admin.searchGroup') }} actions={<ItsmCreateButton onClick={() => start()} />} />
        <CustomTable queryKey={keyword}
          rowKey="id"
          dataSource={shown}
          locale={{ emptyText: t('itsm.admin.emptyGroup') }}
          columns={[
            { title: t('itsm.portal.name'), dataIndex: 'name', key: 'name', render: (value: string, item: HandlerGroupItem) => <ItsmListEntry onClick={() => start(item)}>{value}</ItsmListEntry> },
            { title: t('itsm.admin.leader'), dataIndex: 'leaders', key: 'leaders', render: (leaders: string[]) => leaders?.length ? leaders.map((user) => <Tag key={user}>{user}</Tag>) : '—' },
            { title: t('itsm.admin.members'), dataIndex: 'members', key: 'members', render: (value: string[]) => value?.join('、') || '—' },
            { fixed: 'right' as const, width: 120,
              title: t('itsm.ticket.action'),
              key: 'actions',
              render: (_value: unknown, item: HandlerGroupItem) => <ItsmRowActions items={[{key: 'action-0', label: t('itsm.common.edit'), kind: 'edit' as const, onClick: () => start(item)},
                {key: 'action-1', label: t('itsm.common.delete'), kind: 'delete' as const, danger: true, confirm: {title: t('itsm.admin.deleteGroup'), content: undefined }, onClick: () => { void api.deleteHandlerGroup(item.id).then(load); }}]} />,
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
