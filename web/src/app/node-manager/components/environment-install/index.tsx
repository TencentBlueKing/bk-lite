'use client';

import React, { useEffect, useRef, useState } from 'react';
import { Alert, Button, Form, Input, InputNumber, Modal, Popconfirm, Select, Space, Table, Tabs, Typography, message } from 'antd';
import type { AxiosResponse } from 'axios';
import useApiClient from '@/utils/request';
import { useTranslation } from '@/utils/i18n';
import { useUserInfoContext } from '@/context/userInfo';
import { parseContentDispositionFilename } from '@/app/node-manager/utils/nodeListExport';

interface Grant { id: string; cloud_region_id: number; package_version: string; used_nodes: number; max_nodes: number; enabled: boolean; expires_at: string }
interface GrantPage { count: number; items: Grant[] }
interface Attempt {
  id: string; node_id: string; ip: string; node_name: string; registered_at: string | null;
  failure_stage: string; error_code: number; components_healthy?: boolean; executor_rpc_ready?: boolean | null;
}
const EXPORT_ERROR_KEYS: Record<string, string> = {
  package_digest_missing: 'exportDigestMissing',
  ca_invalid: 'exportCaInvalid',
  install_script_invalid: 'exportScriptInvalid',
};

async function exportErrorKey(error: unknown) {
  const payload = (error as { payload?: unknown })?.payload;
  let body = payload;
  if (payload instanceof Blob) {
    try { body = JSON.parse(await payload.text()); } catch { body = null; }
  }
  const code = body && typeof body === 'object' && 'data' in body
    ? (body as { data?: { error_code?: string } }).data?.error_code
    : undefined;
  return code && EXPORT_ERROR_KEYS[code] ? EXPORT_ERROR_KEYS[code] : 'exportFailed';
}

function attemptState(row: Attempt) {
  if (row.registered_at && row.components_healthy) return 'stateReady';
  if (row.registered_at) return 'stateRegisteredUnready';
  if (row.error_code) return 'stateFailed';
  return 'statePending';
}
interface AttemptPage { count: number; items: Attempt[] }
interface Package { id: number; version: string; sha256?: string }
interface ComponentOption { id: string; name: string }
interface Values { required_collectors?: string[]; package_id: number; valid_days: number; max_nodes: number; free_mib: number; management_cidr?: string }

export default function EnvironmentInstall({ open, cloudId, onClose }: { open: boolean; cloudId: number; onClose: () => void }) {
  const { t } = useTranslation();
  const label = (key: string) => t(`node-manager.environmentBundle.${key}`);
  const api = useApiClient();
  const apiRef = useRef(api);
  apiRef.current = api;
  const { selectedGroup } = useUserInfoContext();
  const [form] = Form.useForm<Values>();
  const [packages, setPackages] = useState<Package[]>([]);
  const [components, setComponents] = useState<ComponentOption[]>([]);
  const [grants, setGrants] = useState<Grant[]>([]);
  const [grantPage, setGrantPage] = useState(1);
  const [grantTotal, setGrantTotal] = useState(0);
  const [attempts, setAttempts] = useState<Attempt[] | null>(null);
  const [attemptGrant, setAttemptGrant] = useState('');
  const [attemptPage, setAttemptPage] = useState(1);
  const [attemptTotal, setAttemptTotal] = useState(0);
  const [attemptLoading, setAttemptLoading] = useState(false);
  const attemptRequest = useRef(0);
  const [loading, setLoading] = useState(false);
  const [exporting, setExporting] = useState(false);
  const [loadError, setLoadError] = useState(false);
  const [loadRevision, setLoadRevision] = useState(0);
  const [digest, setDigest] = useState('');
  const base = '/node_mgmt/api/environment_install';

  const refresh = async (page = 1) => {
    setLoading(true);
    try {
      const data = await apiRef.current.get<GrantPage>(`${base}/grants/`, { params: { cloud_region_id: cloudId, page, page_size: 10 } });
      setGrants(data.items);
      setGrantTotal(data.count);
      setGrantPage(page);
      if (!data.items.some((item) => item.id === attemptGrant)) {
        setAttempts(null);
        setAttemptGrant('');
      }
    } finally { setLoading(false); }
  };

  const loadAttempts = async (grantId: string, page = 1) => {
    const requestId = ++attemptRequest.current;
    setAttemptLoading(true);
    if (grantId !== attemptGrant) setAttempts(null);
    setAttemptGrant(grantId);
    try {
      const data = await apiRef.current.post<AttemptPage>(`${base}/results/`, { grant_id: grantId, page, page_size: 10 });
      if (requestId !== attemptRequest.current) return;
      setAttempts(data.items);
      setAttemptTotal(data.count);
      setAttemptPage(page);
    } catch {
      if (requestId === attemptRequest.current) {
        setAttempts(null);
        message.error(label('loadFailed'));
      }
    } finally {
      if (requestId === attemptRequest.current) setAttemptLoading(false);
    }
  };

  useEffect(() => {
    if (!open) return;
    let active = true;
    setAttempts(null);
    setAttemptGrant('');
    setAttemptLoading(false);
    setDigest('');
    setGrants([]);
    setGrantPage(1);
    setGrantTotal(0);
    setPackages([]);
    setComponents([]);
    setLoadError(false);
    form.resetFields();
    setLoading(true);
    Promise.all([
      apiRef.current.get<{ count: number; items: Package[] }>('/node_mgmt/api/package/', { params: { os: 'linux', cpu_architecture: 'x86_64', type: 'controller', object: 'Controller', page_size: 100 } }),
      apiRef.current.get<GrantPage>(`${base}/grants/`, { params: { cloud_region_id: cloudId, page: 1, page_size: 10 } }),
      apiRef.current.get<ComponentOption[]>(`${base}/components/`, { params: { cloud_region_id: cloudId } })
    ]).then(([versions, items, options]) => {
      if (!active) return;
      const rows = versions.items;
      setComponents(options.filter((item) => item.name !== 'NATS-Executor'));
      setPackages(rows.filter((item) => item.version !== 'latest' && item.sha256?.length === 64));
      setGrants(items.items);
      setGrantTotal(items.count);
    }).catch(() => { if (active) setLoadError(true); }).finally(() => { if (active) setLoading(false); });
    return () => { active = false; attemptRequest.current += 1; };
  }, [open, cloudId, selectedGroup?.id, form, loadRevision]);

  const exportBundle = async () => {
    const values = await form.validateFields();
    if (!selectedGroup?.id) return;
    setExporting(true);
    try {
      const response = await apiRef.current.post<{ data: Blob; headers: AxiosResponse['headers'] }>(`${base}/export/`, {
        cloud_region_id: cloudId, organization: Number(selectedGroup.id), package_id: values.package_id,
        required_collectors: values.required_collectors || [],
        valid_days: values.valid_days, max_nodes: values.max_nodes, required_free_bytes: values.free_mib * 1024 * 1024,
        management_cidr: values.management_cidr || '', timeout_seconds: 900
      }, { responseType: 'blob', blobMeta: true, suppressErrorNotification: true });
      const hash = response.headers?.['x-artifact-sha256'];
      if (typeof hash !== 'string' || !/^[a-f0-9]{64}$/.test(hash)) throw new Error('invalid artifact response');
      const filename = parseContentDispositionFilename(response.headers?.['content-disposition']) || 'install-controller.run';
      const url = URL.createObjectURL(response.data);
      const anchor = document.createElement('a');
      anchor.href = url; anchor.download = filename; anchor.click();
      setTimeout(() => URL.revokeObjectURL(url), 1000);
      setDigest(hash);
      await refresh(1);
    } catch (error) { message.error(label(await exportErrorKey(error))); }
    finally { setExporting(false); }
  };

  const revoke = async (grant: Grant) => {
    await apiRef.current.post(`${base}/revoke/`, { grant_id: grant.id });
    await refresh(grantPage);
  };

  return <Modal open={open} onCancel={onClose} title={label('title')} width={900} footer={null} destroyOnClose>
    <Alert type="info" showIcon message={label('scope')} description={`${label('organization')}: ${selectedGroup?.name || selectedGroup?.id || '-'} · Linux x86_64 · systemd`} className="mb-4" />
    {loadError && <Alert type="error" showIcon message={label('loadFailed')} className="mb-4" action={<Button onClick={() => setLoadRevision((value) => value + 1)}>{t('common.refresh')}</Button>} />}
    <Tabs items={[
      { key: 'export', label: label('exportTab'), children: <>
        <Form form={form} layout="vertical" initialValues={{ valid_days: 7, max_nodes: 100, required_collectors: [] }}>
          <Form.Item name="package_id" label={label('version')} rules={[{ required: true }]} extra={!loading && !loadError && packages.length === 0 ? label('noVersion') : undefined}>
            <Select loading={loading} options={packages.map((item) => ({ value: item.id, label: item.version }))} placeholder={label('selectVersion')} />
          </Form.Item>
          <Form.Item name="required_collectors" label={label('components')} extra={label('componentsHelp')}>
            <Select mode="multiple" allowClear loading={loading} options={components.map((item) => ({ value: item.id, label: item.name }))} />
          </Form.Item>
          <div className="grid grid-cols-1 gap-x-4 md:grid-cols-3">
            <Form.Item name="valid_days" label={label('days')} rules={[{ required: true }]}><InputNumber min={1} max={30} precision={0} className="w-full" /></Form.Item>
            <Form.Item name="max_nodes" label={label('quota')} rules={[{ required: true }]}><InputNumber min={1} max={10000} precision={0} className="w-full" /></Form.Item>
            <Form.Item name="free_mib" label={label('space')} tooltip={label('spaceHelp')} rules={[{ required: true }]}><InputNumber min={128} precision={0} className="w-full" /></Form.Item>
          </div>
          <Form.Item name="management_cidr" label={label('network')} extra={label('networkHelp')}><Input placeholder="192.168.1.0/24" /></Form.Item>
          <p className="mb-4">{label('caHelp')}</p>
          <Alert type="warning" showIcon message={label('sensitive')} className="mb-4" />
          <Button type="primary" loading={exporting} disabled={loading || loadError || packages.length === 0 || !selectedGroup?.id} onClick={exportBundle}>{label('download')}</Button>
        </Form>
        {digest && <div className="mt-4 break-all"><Typography.Text copyable>SHA-256: {digest}</Typography.Text><p className="mt-2">{label('command')}</p></div>}
      </> },
      { key: 'grants', label: label('grantsTab'), children: <>
        <Button onClick={() => refresh(grantPage)} loading={loading} className="mb-3">{t('common.refresh')}</Button>
        <p className="mb-3 text-[var(--color-text-3)]">{label('usedQuotaHelp')}</p>
        <Table<Grant> rowKey="id" size="small" loading={loading} dataSource={grants} pagination={{ current: grantPage, total: grantTotal, pageSize: 10, showSizeChanger: false, onChange: (page) => { void refresh(page); } }} scroll={{ x: 750 }} columns={[
          { title: label('id'), dataIndex: 'id', ellipsis: true },
          { title: label('version'), dataIndex: 'package_version' },
          { title: label('usedQuota'), render: (_, row) => `${row.used_nodes}/${row.max_nodes}` },
          { title: label('expires'), dataIndex: 'expires_at', render: (value: string) => new Date(value).toLocaleString() },
          { title: t('common.actions'), render: (_, row) => <Space>
            <Button type="link" onClick={() => loadAttempts(row.id)}>{label('results')}</Button>
            <Popconfirm title={label('revokeConfirm')} onConfirm={() => revoke(row)} disabled={!row.enabled}><Button type="link" danger disabled={!row.enabled}>{row.enabled ? label('revoke') : label('revoked')}</Button></Popconfirm>
          </Space> }
        ]} />
        {attempts && <>
          <p className="mb-2 mt-4">{label('results')}: {attemptGrant}</p>
          <Table<Attempt> rowKey="id" size="small" loading={attemptLoading} dataSource={attempts} pagination={{ current: attemptPage, total: attemptTotal, pageSize: 10, showSizeChanger: false, onChange: (page) => { void loadAttempts(attemptGrant, page); } }} scroll={{ x: 800 }} columns={[
            { title: label('host'), dataIndex: 'node_name' }, { title: 'IP', dataIndex: 'ip' }, { title: 'Node ID', dataIndex: 'node_id', ellipsis: true },
            { title: label('state'), render: (_, row) => row.error_code && !row.registered_at ? `${label(attemptState(row))} (${row.failure_stage || '-'})` : label(attemptState(row)) },
            { title: label('firstSeen'), dataIndex: 'registered_at', render: (value: string | null) => value ? new Date(value).toLocaleString() : label('statePending') },
            { title: label('exitCode'), dataIndex: 'error_code' }
          ]} />
        </>}
      </> }
    ]} />
  </Modal>;
}
