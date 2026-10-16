'use client';

import { useState, type MouseEvent } from 'react';
import { Button, Modal, Popconfirm, Select } from 'antd';

import { useRumQueries, type RumAlertItem, type RumNotificationRecipient } from '@/app/rum/api';
import RumPermission from '@/app/rum/components/rum-permission';
import { useUserInfoContext } from '@/context/userInfo';
import { useTranslation } from '@/utils/i18n';

function isCurrentHandler(handlers: RumAlertItem['handlers'], actor: { id?: string; username?: string }) {
  const candidates = new Set([actor.id, actor.username].filter(Boolean).map(String));
  return (handlers || []).some((item) => candidates.has(String(item)));
}

export function canClaimOrAssign(alert: RumAlertItem) {
  return alert.status === 'active' && !(alert.handlers || []).length;
}

export function canReassign(alert: RumAlertItem, actor: { id?: string; username?: string }) {
  return alert.status === 'active' && isCurrentHandler(alert.handlers, actor);
}

export function canClose(alert: RumAlertItem, actor: { id?: string; username?: string }) {
  return alert.status === 'active' && (!(alert.handlers || []).length || isCurrentHandler(alert.handlers, actor));
}

export default function AlertHandlerActions({
  alert,
  onDone,
}: {
  alert: RumAlertItem;
  onDone: () => void;
}) {
  const { t } = useTranslation();
  const { userId, username } = useUserInfoContext();
  const { claimAlert, assignAlert, reassignAlert, closeAlert, searchNotificationRecipients } = useRumQueries();
  const actor = { id: userId, username };
  const [open, setOpen] = useState(false);
  const [mode, setMode] = useState<'assign' | 'reassign'>('assign');
  const [users, setUsers] = useState<RumNotificationRecipient[]>([]);
  const [selected, setSelected] = useState<string[]>([]);
  const [pending, setPending] = useState(false);

  async function openModal(next: 'assign' | 'reassign', event?: MouseEvent) {
    event?.stopPropagation();
    const found = await searchNotificationRecipients(alert.organizations || [], '').catch(() => []);
    setUsers(found);
    setSelected([]);
    setMode(next);
    setOpen(true);
  }

  async function submitHandlers() {
    if (!selected.length) return;
    setPending(true);
    try {
      if (mode === 'reassign') await reassignAlert(alert.id, selected);
      else await assignAlert(alert.id, selected);
      setOpen(false);
      onDone();
    } catch {
      // request toast is handled by useApiClient
    } finally {
      setPending(false);
    }
  }

  return (
    <RumPermission resource="alert-events" action="Operate" className="inline-flex items-center gap-2">
      {canClaimOrAssign(alert) ? (
        <>
          <Popconfirm
            title={t('rum.alertEvents.claimConfirm', '确认认领该告警？')}
            onConfirm={() => {
              setPending(true);
              void claimAlert(alert.id).then(onDone).catch(() => undefined).finally(() => setPending(false));
            }}
          >
            <Button type="link" size="small" className="px-0" loading={pending} onClick={(event) => event.stopPropagation()}>
              {t('rum.alertEvents.claim', '认领')}
            </Button>
          </Popconfirm>
          <Button type="link" size="small" className="px-0" onClick={(event) => void openModal('assign', event)}>
            {t('rum.alertEvents.assign', '分派')}
          </Button>
        </>
      ) : null}
      {canReassign(alert, actor) ? (
        <Button type="link" size="small" className="px-0" onClick={(event) => void openModal('reassign', event)}>
          {t('rum.alertEvents.reassign', '转派')}
        </Button>
      ) : null}
      {canClose(alert, actor) ? (
        <Popconfirm
          title={t('rum.alertEvents.closeConfirm', '确认关闭该告警？')}
          onConfirm={() => {
            setPending(true);
            void closeAlert(alert.id).then(onDone).catch(() => undefined).finally(() => setPending(false));
          }}
        >
          <Button type="link" size="small" className="px-0" loading={pending} onClick={(event) => event.stopPropagation()}>
            {t('rum.alertEvents.close', '关闭')}
          </Button>
        </Popconfirm>
      ) : null}
      <Modal
        open={open}
        title={mode === 'reassign' ? t('rum.alertEvents.reassign', '转派') : t('rum.alertEvents.assign', '分派')}
        onCancel={() => setOpen(false)}
        onOk={() => void submitHandlers()}
        confirmLoading={pending}
        okButtonProps={{ disabled: selected.length === 0 }}
      >
        <Select
          mode="multiple"
          className="w-full"
          value={selected}
          onChange={setSelected}
          options={users.map((item) => ({
            value: String(item.id),
            label: item.display_name ? `${item.display_name} (${item.username})` : item.username,
          }))}
        />
      </Modal>
    </RumPermission>
  );
}
