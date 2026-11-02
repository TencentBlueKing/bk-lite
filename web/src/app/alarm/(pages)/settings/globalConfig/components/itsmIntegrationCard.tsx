'use client';

import React, { useCallback, useEffect, useRef, useState } from 'react';
import { Alert, Button, Collapse, Descriptions, Drawer, Form, Input, Select, Skeleton, Switch, Tag } from 'antd';
import PermissionWrapper from '@/components/permission';
import useApiClient from '@/utils/request';
import { useTranslation } from '@/utils/i18n';

interface Integration {
  reference?: string;
  name: string;
  url: string;
  enabled: boolean;
  token_configured?: boolean;
  ca_pem?: string;
  failure_notification: { usernames?: string[]; channel_ids?: number[] };
}
interface FormValues extends Omit<Integration, 'failure_notification'> {
  token?: string;
  usernames: string[];
  channel_ids: number[];
}
interface Option { label: string; value: string }
interface Props { users: Option[]; channels: { label: string; value: number }[] }
const endpoint = '/alerts/api/itsm_integration/';

export default function ItsmIntegrationCard({ users, channels }: Props) {
  const { t } = useTranslation();
  const { get, put, post } = useApiClient();
  const [config, setConfig] = useState<Integration | null>(null);
  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState(false);
  const [open, setOpen] = useState(false);
  const [saving, setSaving] = useState(false);
  const [testing, setTesting] = useState(false);
  const [feedback, setFeedback] = useState<'success' | 'error' | null>(null);
  const [testError, setTestError] = useState('');
  const [requiresTest, setRequiresTest] = useState(true);
  const [saveError, setSaveError] = useState('');
  const testVersion = useRef(0);
  const [form] = Form.useForm<FormValues>();
  const enabled = Form.useWatch('enabled', form);
  const load = useCallback(async () => {
    setLoading(true);
    try { setConfig(await get<Integration | null>(endpoint)); setLoadError(false); }
    catch { setLoadError(true); }
    finally { setLoading(false); }
  }, [get]);
  useEffect(() => { void load(); return () => { testVersion.current += 1; }; }, [load]);
  const resetTest = () => {
    testVersion.current += 1;
    setTesting(false); setFeedback(null); setTestError('');
  };
  const close = () => {
    if (saving) return;
    resetTest(); setOpen(false); form.resetFields();
  };
  const edit = () => {
    resetTest();
    setRequiresTest(!config?.enabled);
    form.resetFields();
    form.setFieldsValue({
      name: config?.name || 'ITSM', url: config?.url || '', enabled: config?.enabled || false,
      token: '', ca_pem: config?.ca_pem || '',
      usernames: config?.failure_notification?.usernames || [], channel_ids: config?.failure_notification?.channel_ids || [],
    });
    setSaveError(''); setOpen(true);
  };
  const requestBody = (values: FormValues) => {
    const { token, usernames, channel_ids, ...fields } = values;
    return { ...fields, ...(token?.trim() ? { token: token.trim() } : {}), failure_notification: { usernames, channel_ids } };
  };
  const save = async () => {
    const values = await form.validateFields().catch(() => null);
    if (!values) return;
    if (values.enabled && feedback !== 'success' && requiresTest) {
      setSaveError(t('itsmIntegration.testRequired')); return;
    }
    setSaving(true); setSaveError('');
    try {
      setConfig(await put<Integration>(endpoint + 'configure/', requestBody(values), { suppressErrorNotification: true }));
      resetTest(); form.resetFields(); setOpen(false);
    } catch (error) {
      resetTest(); setRequiresTest(true);
      if (!config?.enabled) form.setFieldValue('enabled', false);
      setSaveError(error instanceof Error ? error.message : t('itsmIntegration.saveFailed'));
    }
    finally { setSaving(false); }
  };
  const test = async () => {
    resetTest(); setSaveError(''); setRequiresTest(true);
    if (!config?.enabled) form.setFieldValue('enabled', false);
    const version = testVersion.current;
    const values = await form.validateFields(['name', 'url', 'token', 'ca_pem']).catch(() => null);
    if (!values || version !== testVersion.current) return;
    setTesting(true);
    try {
      const result = await post<{ connected: boolean }>(endpoint + 'test_connection/', requestBody(form.getFieldsValue()), { suppressErrorNotification: true });
      if (version !== testVersion.current) return;
      if (!result.connected) throw new Error(t('itsmIntegration.testFailed'));
      setFeedback('success');
    } catch (error) {
      if (version !== testVersion.current) return;
      setFeedback('error'); setTestError(error instanceof Error ? error.message : '');
    } finally { if (version === testVersion.current) setTesting(false); }
  };
  return <section className="mt-4 rounded-lg border border-[var(--color-border-1)] p-4">
    <div className="flex flex-wrap items-center justify-between gap-3">
      <div className="flex items-center gap-2">
        <h3 className="m-0 text-sm font-semibold">{t('itsmIntegration.title')}</h3>
        {!loading && !loadError && <Tag color={config?.enabled ? 'success' : 'default'}>{t(config?.enabled ? 'itsmIntegration.enabled' : 'itsmIntegration.disabled')}</Tag>}
      </div>
      <div className="flex gap-2">
        <Button disabled={open} onClick={() => void load()} loading={loading}>{t('common.refresh')}</Button>
        <PermissionWrapper requiredPermissions={['Edit']}>
          <Button type="primary" disabled={loading || loadError} onClick={edit}>{t('itsmIntegration.configure')}</Button>
        </PermissionWrapper>
      </div>
    </div>
    <p className="mt-2 text-[var(--color-text-3)]">{t('itsmIntegration.description')}</p>
    {loading ? <Skeleton active paragraph={{ rows: 2 }} /> : loadError ? <Alert type="error" message={t('itsmIntegration.loadFailed')} /> : config ?
      <Descriptions size="small" column={{ xs: 1, sm: 2 }} items={[
        { key: 'name', label: t('itsmIntegration.name'), children: config.name },
        { key: 'auth', label: t('itsmIntegration.authentication'), children: config.token_configured ? t('itsmIntegration.tokenSaved') : t('itsmIntegration.tokenMissing') },
        { key: 'url', label: t('itsmIntegration.url'), children: <span className="break-all">{config.url}</span> },
      ]} /> : <Alert type="info" message={t('itsmIntegration.empty')} />}
    <Drawer open={open} onClose={close} title={t('itsmIntegration.title')} width={640}
      footer={<div className="flex justify-end gap-2"><Button disabled={saving} onClick={close}>{t('common.cancel')}</Button><Button type="primary" disabled={testing || (enabled && requiresTest && feedback !== 'success')} loading={saving} onClick={() => void save()}>{t('common.save')}</Button></div>}>
      {saveError && <Alert className="mb-4" type="error" message={t('itsmIntegration.saveFailed')} description={saveError} />}
      <Form form={form} layout="vertical" disabled={saving} onValuesChange={(changed: Partial<FormValues>) => {
        if (['url', 'token', 'ca_pem'].some(key => key in changed)) {
          resetTest(); setSaveError(''); setRequiresTest(true);
          if (!config?.enabled) form.setFieldValue('enabled', false);
        }
      }}>
        <Form.Item name="name" label={t('itsmIntegration.name')} rules={[{ required: true, whitespace: true }]}><Input maxLength={100} /></Form.Item>
        <Form.Item name="url" label={t('itsmIntegration.url')} rules={[{ required: true }, { pattern: /^https:\/\//, message: t('itsmIntegration.httpsRequired') }]} extra={t('itsmIntegration.urlHint')}><Input maxLength={1024} /></Form.Item>
        <Form.Item name="token" label={t('itsmIntegration.token')} rules={[{ required: !config?.token_configured }]} extra={t('itsmIntegration.tokenHint')}><Input.Password autoComplete="new-password" maxLength={8192} /></Form.Item>
        <Form.Item name="ca_pem" label={t('itsmIntegration.ca')} extra={t('itsmIntegration.caHint')}><Input.TextArea rows={3} maxLength={32768} /></Form.Item>
        <div className="mb-4"><Button aria-label={t('itsmIntegration.test')} loading={testing} disabled={saving || testing} onClick={() => void test()}>{t('itsmIntegration.test')}</Button></div>
        {feedback && <Alert className="mb-4" type={feedback} message={t(feedback === 'success' ? 'itsmIntegration.testPassed' : 'itsmIntegration.testFailed')} description={feedback === 'error' ? testError : undefined} />}
        <Form.Item name="enabled" label={t('itsmIntegration.enabled')} valuePropName="checked" extra={t(feedback === 'success' || enabled ? 'itsmIntegration.enableHint' : 'itsmIntegration.testRequired')}><Switch disabled={saving || (!enabled && feedback !== 'success')} /></Form.Item>
        <Collapse items={[{ key: 'notification', label: t('itsmIntegration.failureNotification'), forceRender: true, children: <>
          <Form.Item name="usernames" label={t('itsmIntegration.recipients')}><Select mode="multiple" options={users} optionFilterProp="label" /></Form.Item>
          <Form.Item name="channel_ids" label={t('itsmIntegration.channels')}><Select mode="multiple" options={channels} optionFilterProp="label" /></Form.Item>
        </> }]} />
      </Form>
    </Drawer>
  </section>;
}
