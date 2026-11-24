'use client';

import { ItsmListEntry } from '@/app/itsm/components/list-entry';

import { ItsmRowActions, ItsmListToolbar, ItsmCreateButton } from '@/app/itsm/components/list-controls';

import { Input, Select, Tag, message } from 'antd';
import { useCallback, useEffect, useState } from 'react';
import { ItsmModal as OperateModal } from '@/app/itsm/components/interaction-surfaces';
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
  const [leaders, setLeaders] = useState<string[]>([]);
  const [canEdit, setCanEdit] = useState(false);

  const load = useCallback(async () => {
    const data = await api.listHandlerGroups() as { items?: HandlerGroupItem[]; can_edit?: boolean };
    setItems(data.items || []);
    setCanEdit(data.can_edit === true);
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
    setLeaders(item?.leaders || []);
    setOpen(true);
  };

  const save = async () => {
    if (!canEdit) return;
    if (!name.trim()) {
      message.warning(t('itsm.admin.needGroup'));
      return;
    }
    await api.createHandlerGroup({ id: editing?.id, name: name.trim(), members, leaders });
    setOpen(false);
    message.success(editing ? t('itsm.portal.saved') : t('itsm.portal.created'));
    await load();
  };

  const shown = items.filter((item) => !keyword.trim() || item.name.includes(keyword.trim()));

  return (
    <div className="flex flex-col gap-4">
      <div className="rounded-lg border border-[var(--color-border)] bg-[var(--color-bg)] p-4">
        <ItsmListToolbar search={{ value: keyword, onChange: setKeyword, placeholder: t('itsm.admin.searchGroup') }} actions={canEdit && <ItsmCreateButton onClick={() => start()} />} />
        <CustomTable queryKey={keyword}
          rowKey="id"
          dataSource={shown}
          locale={{ emptyText: t('itsm.admin.emptyGroup') }}
          columns={[
            { title: t('itsm.portal.name'), dataIndex: 'name', key: 'name', render: (value: string, item: HandlerGroupItem) => canEdit ? <ItsmListEntry onClick={() => start(item)}>{value}</ItsmListEntry> : value },
            { title: t('itsm.admin.leader'), dataIndex: 'leaders', key: 'leaders', render: (leaders: string[]) => leaders?.length ? leaders.map((user) => <Tag key={user}>{user}</Tag>) : '—' },
            { title: t('itsm.admin.members'), dataIndex: 'members', key: 'members', render: (value: string[]) => value?.join('、') || '—' },
            ...(canEdit ? [{ fixed: 'right' as const, width: 120,
              title: t('itsm.ticket.action'),
              key: 'actions',
              render: (_value: unknown, item: HandlerGroupItem) => <ItsmRowActions items={[{key: 'action-0', label: t('itsm.common.edit'), kind: 'edit' as const, onClick: () => start(item)},
                {key: 'action-1', label: t('itsm.common.delete'), kind: 'delete' as const, danger: true, confirm: {title: t('itsm.admin.deleteGroup'), content: undefined }, onClick: () => { void api.deleteHandlerGroup(item.id).then(load); }}]} />,
            }] : []),
          ]}
        />
      </div>
      <OperateModal formValue={{ name, members, leaders }} title={editing ? t('itsm.admin.editGroup') : t('itsm.admin.newGroup')} open={open} onCancel={() => setOpen(false)} onOk={save}>
        <div className="flex flex-col gap-3">
          <FieldRow label={t('itsm.portal.name')}>
            <Input placeholder={t('itsm.admin.groupName')} value={name} onChange={(event) => setName(event.target.value)} />
          </FieldRow>
          <FieldRow label={t('itsm.admin.members')}>
            <UserSelector ariaLabel={t('itsm.admin.members')} value={members} onChange={next => {
              setMembers(next);
              setLeaders(current => current.filter(leader => next.includes(leader)));
            }} />
          </FieldRow>
          <FieldRow label={t('itsm.admin.leader')}>
            <Select aria-label={t('itsm.admin.leader')} mode="multiple" className="w-full" value={leaders}
              placeholder="从组成员中选择负责人" options={members.map(member => ({ value: member, label: member }))}
              onChange={setLeaders} />
          </FieldRow>
        </div>
      </OperateModal>
    </div>
  );
}
