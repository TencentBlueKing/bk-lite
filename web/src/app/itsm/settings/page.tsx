'use client';

import { Button, Input, Select, Switch, message } from 'antd';
import { useEffect, useState } from 'react';
import { useItsmApi } from '../api/useItsmApi';
import { FieldRow } from '../components/field-row';
import { useTranslation } from '@/utils/i18n';
import { defaultBasicSettings, useItsmRuntimeSettings, type BasicSettings } from './runtime-settings';

export default function SettingsPage() {
  const { t } = useTranslation();
  const api = useItsmApi();
  const { updateSettings } = useItsmRuntimeSettings();
  const [form, setForm] = useState<BasicSettings>(defaultBasicSettings);
  const [canEdit, setCanEdit] = useState(false);
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    if (!api.ready) return;
    let current = true;
    void api.getBasicSettings().then(value => {
      if (!current) return;
      const { can_edit, ...data } = value as BasicSettings & { can_edit: boolean };
      setForm({ ...defaultBasicSettings, ...data });
      setCanEdit(can_edit);
    }).catch(error => {
      if (current) message.error(error instanceof Error ? error.message : t('itsm.ticket.loadFailed'));
    });
    return () => { current = false; };
  }, [api.ready, api.getBasicSettings, t]);

  const save = async () => {
    if (!canEdit || saving) return;
    setSaving(true);
    try {
      const saved = await api.saveBasicSettings(form) as BasicSettings;
      setForm(saved);
      updateSettings(saved);
      message.success(t('itsm.admin.saved'));
    } catch (error) {
      message.error(error instanceof Error ? error.message : '保存失败');
    } finally {
      setSaving(false);
    }
  };
  const disabled = !canEdit || saving;

  return (
    <div className="flex flex-col gap-4">
      <div className="flex items-center justify-between rounded-lg border border-[var(--color-border)] bg-[var(--color-bg)] px-4 py-3">
        <div className="text-sm font-medium text-[var(--color-text-1)]">{t('itsm.admin.basic')}</div>
        {canEdit && <Button type="primary" loading={saving} onClick={() => { void save(); }}>{t('itsm.common.save')}</Button>}
      </div>
      <div className="flex flex-col gap-4 rounded-lg border border-[var(--color-border)] bg-[var(--color-bg)] p-4">
        <FieldRow label={t('itsm.admin.productName')}>
          <Input aria-label={t('itsm.admin.productName')} maxLength={100} disabled={disabled} value={form.product_name} onChange={event => setForm({ ...form, product_name: event.target.value })} />
        </FieldRow>
        <FieldRow label={t('itsm.admin.tabTitle')}>
          <Input aria-label={t('itsm.admin.tabTitle')} maxLength={100} disabled={disabled} value={form.tab_title} onChange={event => setForm({ ...form, tab_title: event.target.value })} />
        </FieldRow>
        <FieldRow label={t('itsm.admin.attachmentTypes')} align="start">
          <Input aria-label={t('itsm.admin.attachmentTypes')} placeholder="pdf,png,jpg" disabled={disabled} value={form.attachment_types} onChange={event => setForm({ ...form, attachment_types: event.target.value })} />
          <p className="mt-1 text-xs text-[var(--color-text-3)]">用逗号分隔文件扩展名。留空时允许所有文件扩展名。</p>
        </FieldRow>
        <FieldRow label={t('itsm.admin.userDisplay')}>
          <Select
            aria-label={t('itsm.admin.userDisplay')}
            className="w-full"
            disabled={disabled}
            value={form.user_display}
            options={[{ value: 'display_name', label: t('itsm.admin.displayName') }, { value: 'username', label: t('itsm.admin.username') }]}
            onChange={value => setForm({ ...form, user_display: value })}
          />
        </FieldRow>
        <FieldRow label={t('itsm.admin.showLog')} align="start">
          <Switch aria-label={t('itsm.admin.showLog')} disabled={disabled} checked={form.show_process_log} onChange={checked => setForm({ ...form, show_process_log: checked })} />
        </FieldRow>
      </div>
    </div>
  );
}
