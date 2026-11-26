'use client';

import { Alert, App, Button, Switch } from 'antd';
import { useCallback, useEffect, useState } from 'react';
import { ItsmListEntry } from '@/app/itsm/components/list-entry';
import { ItsmRowActions, ItsmListToolbar, ItsmCreateButton } from '@/app/itsm/components/list-controls';
import ItsmListTable from '@/app/itsm/components/itsm-list-table';
import { useTranslation } from '@/utils/i18n';
import { useItsmApi } from '../../api/useItsmApi';
import { TriggerEditor } from './trigger-editor';
import { readTriggerActions, TRIGGER_ACTIONS, type TriggerItem } from './trigger-config';

interface TriggerList {
  items: TriggerItem[];
  can_add?: boolean;
  can_edit?: boolean;
  can_delete?: boolean;
}

export default function Page() {
  const { t } = useTranslation();
  const { message } = App.useApp();
  const { ready, listResources, getTriggerOptions, createResource, updateResource, deleteResource } = useItsmApi();
  const [keyword, setKeyword] = useState('');
  const [list, setList] = useState<TriggerList>({ items: [] });
  const [editing, setEditing] = useState<TriggerItem | 'new' | null>(null);
  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState(false);
  const [changing, setChanging] = useState<number | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    setLoadError(false);
    try {
      setList(await listResources('triggers') as unknown as TriggerList);
    } catch {
      setLoadError(true);
    } finally {
      setLoading(false);
    }
  }, [listResources]);

  useEffect(() => {
    if (ready) void load();
  }, [ready, load]);

  const toggle = async (id: number, isEnabled: boolean) => {
    setChanging(id);
    try {
      await updateResource('triggers', id, { is_enabled: isEnabled });
      await load();
    } catch (error) {
      message.error(error instanceof Error ? error.message : t('itsm.rule.triggerSaveFailed'));
    } finally {
      setChanging(null);
    }
  };

  const actionLabel = (type: string) => {
    const action = TRIGGER_ACTIONS.find(option => option.value === type);
    return action ? t(`itsm.rule.${action.labelKey}`) : type;
  };
  const query = keyword.trim().toLowerCase();
  const canOperate = list.can_edit || list.can_delete;

  return <div className="flex flex-col gap-4">
    <div className="rounded-lg border border-[var(--color-border)] bg-[var(--color-bg)] p-4">
      <ItsmListToolbar search={{ value: keyword, onChange: setKeyword, placeholder: t('itsm.rule.triggerSearch') }}
        actions={list.can_add && <ItsmCreateButton onClick={() => setEditing('new')} />} />
      {loadError && <Alert className="mb-4" type="error" showIcon message={t('itsm.ticket.loadFailed')}
        action={<Button size="small" onClick={() => void load()}>{t('common.retry')}</Button>} />}
      <ItsmListTable<TriggerItem>
        queryKey={keyword}
        loading={loading}
        rowKey="id"
        dataSource={list.items.filter(item => item.name.toLowerCase().includes(query) || String(item.id).includes(query))}
        locale={{ emptyText: t('itsm.rule.emptyTrigger') }}
        columns={[
          { title: t('itsm.portal.name'), dataIndex: 'name', key: 'name',
            render: (name, item) => <ItsmListEntry onClick={() => setEditing(item)}>{name}</ItsmListEntry> },
          { title: t('itsm.rule.event'), dataIndex: 'event', key: 'event', render: event => t(`itsm.rule.${event}`, event) },
          { title: t('itsm.rule.triggerScope'), key: 'scope',
            render: (_, item) => t(`itsm.rule.triggerScope_${item.config?.scope?.mode ?? 'all'}`) },
          { title: t('itsm.rule.response'), key: 'actions_summary',
            render: (_, item) => readTriggerActions(item).map(action => actionLabel(action.type)).join(' → ') || '—' },
          { title: t('itsm.admin.enable'), dataIndex: 'is_enabled', key: 'is_enabled',
            render: (enabled, item) => <Switch aria-label={item.name} checked={enabled} loading={changing === item.id}
              disabled={!list.can_edit || changing !== null} onChange={checked => void toggle(item.id, checked)} /> },
          ...(canOperate ? [{
            fixed: 'right' as const, width: 120, title: t('itsm.ticket.action'), key: 'operations',
            render: (_: unknown, item: TriggerItem) => <ItsmRowActions items={[
              { key: 'edit', label: t('itsm.common.edit'), kind: 'edit', hidden: !list.can_edit, onClick: () => setEditing(item) },
              { key: 'delete', label: t('itsm.common.delete'), kind: 'delete', hidden: !list.can_delete, danger: true,
                confirm: { title: t('itsm.rule.deleteTrigger') }, onClick: async () => {
                  await deleteResource('triggers', item.id);
                  await load();
                } },
            ]} />,
          }] : []),
        ]}
      />
    </div>
    {editing && <TriggerEditor item={editing === 'new' ? undefined : editing}
      getOptions={getTriggerOptions} onCancel={() => setEditing(null)} onSave={(editing === 'new' ? list.can_add : list.can_edit) ? async payload => {
        if (editing === 'new') await createResource('triggers', payload);
        else await updateResource('triggers', editing.id, payload);
        setEditing(null);
        message.success(t(editing === 'new' ? 'itsm.portal.created' : 'itsm.portal.saved'));
        await load();
      } : undefined} />}
  </div>;
}
