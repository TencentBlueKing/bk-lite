'use client';

import { Button, Input, Select, Switch, message } from 'antd';
import { useCallback, useEffect, useState } from 'react';
import { useItsmApi } from '../api/useItsmApi';
import { FieldRow } from '../components/field-row';
import { useTranslation } from '@/utils/i18n';

interface BasicSettings {
  product_name: string;
  tab_title: string;
  attachment_types: string;
  show_process_log: boolean;
  user_display: string;
}

const empty: BasicSettings = {
  product_name: 'ITSM',
  tab_title: 'ITSM',
  attachment_types: 'png,jpg,pdf,docx,xlsx',
  show_process_log: true,
  user_display: 'display_name',
};

export default function SettingsPage() {
  const { t } = useTranslation();
  const api = useItsmApi();
  const [form, setForm] = useState<BasicSettings>(empty);

  const load = useCallback(async () => {
    const data = await api.getBasicSettings() as BasicSettings;
    setForm({ ...empty, ...data });
  }, [api.getBasicSettings]);

  useEffect(() => {
    if (!api.ready) {
      return;
    }
    void load().catch((error: unknown) => message.error(error instanceof Error ? error.message : t('itsm.ticket.loadFailed')));
  }, [api.ready, load]);

  const save = async () => {
    await api.saveBasicSettings(form);
    message.success(t('itsm.admin.saved'));
  };

  return (
    <div className="flex flex-col gap-4">
      <div className="flex items-center justify-between rounded-lg border border-[var(--color-border)] bg-[var(--color-bg)] px-4 py-3">
        <div className="text-sm font-medium text-[var(--color-text-1)]">{t('itsm.admin.basic')}</div>
        <Button type="primary" onClick={() => { void save(); }}>{t('itsm.common.save')}</Button>
      </div>
      <div className="flex flex-col gap-4 rounded-lg border border-[var(--color-border)] bg-[var(--color-bg)] p-4">
        <FieldRow label={t('itsm.admin.productName')}>
          <Input value={form.product_name} onChange={(event) => setForm({ ...form, product_name: event.target.value })} />
        </FieldRow>
        <FieldRow label={t('itsm.admin.tabTitle')}>
          <Input value={form.tab_title} onChange={(event) => setForm({ ...form, tab_title: event.target.value })} />
        </FieldRow>
        <FieldRow label={t('itsm.admin.attachmentTypes')}>
          <Input value={form.attachment_types} onChange={(event) => setForm({ ...form, attachment_types: event.target.value })} />
        </FieldRow>
        <FieldRow label={t('itsm.admin.userDisplay')}>
          <Select
            className="w-full"
            value={form.user_display}
            options={[{ value: 'display_name', label: t('itsm.admin.displayName') }, { value: 'username', label: t('itsm.admin.username') }]}
            onChange={(value) => setForm({ ...form, user_display: value })}
          />
        </FieldRow>
        <FieldRow label={t('itsm.admin.showLog')} align="start">
          <Switch checked={form.show_process_log} onChange={(checked) => setForm({ ...form, show_process_log: checked })} />
        </FieldRow>
      </div>
    </div>
  );
}
