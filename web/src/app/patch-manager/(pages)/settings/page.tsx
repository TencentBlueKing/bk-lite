'use client';

import React, { useState, useEffect, useRef } from 'react';
import { Tag, Button, Tabs, Input, Select, Space, TimePicker, Alert, message, Form, Switch, Modal, InputNumber, Spin, Popconfirm } from 'antd';
import PermissionWrapper from '@/components/permission';
import Password from '@/components/password';
import type { Dayjs } from 'dayjs';
import dayjs from 'dayjs';
import { PlusOutlined, ClockCircleOutlined, LinkOutlined, EditOutlined, PlayCircleOutlined, CheckCircleOutlined } from '@ant-design/icons';
import CustomTable from '@/components/custom-table';
import type { ColumnsType } from 'antd/es/table';
import useApiClient from '@/utils/request';
import usePatchManagerApi from '@/app/patch-manager/api';
import type { PatchSource, PatchSourceType } from '@/app/patch-manager/types';
import styles from './page.module.scss';
import { useLocalizedTime } from '@/hooks/useLocalizedTime';
import { useTranslation } from '@/utils/i18n';
import { createListRequestCoordinator } from '@/app/patch-manager/utils/list-request-coordinator';

const SOURCE_TYPE_OPTIONS: { label: string; value: PatchSourceType }[] = [
  { label: 'WSUS', value: 'wsus' },
  { label: 'yum repo', value: 'yum_repo' },
  { label: 'dnf repo', value: 'dnf_repo' },
  { label: 'apt repo', value: 'apt_repo' },
];

const SAVED_SECRET = '********';

function getConnStatusKey(status?: string) {
  if (status === 'connected') return 'connected';
  if (status === 'failed') return 'failed';
  return 'undetected';
}

function getConnColor(status?: string) {
  if (status === 'connected') return '#52c41a';
  if (status === 'failed') return '#ff4d4f';
  if (status === 'detecting') return '#faad14';
  return '#8c8c8c';
}

function inferDistro(type: PatchSourceType, url: string) {
  if (type === 'wsus') return 'Windows Server';
  const lower = url.toLowerCase();
  if (lower.includes('rocky')) return 'Rocky Linux';
  if (lower.includes('centos')) return 'CentOS';
  if (lower.includes('rhel') || lower.includes('redhat')) return 'RHEL';
  if (lower.includes('ubuntu')) return 'Ubuntu';
  if (lower.includes('debian')) return 'Debian';
  return '';
}

function SourcesTab({ activeKey }: { activeKey: string }) {
  const { t } = useTranslation();
  const api = usePatchManagerApi();
  const { isLoading: authLoading } = useApiClient();
  const [selectedSources, setSelectedSources] = useState<React.Key[]>([]);
  const [sources, setSources] = useState<PatchSource[]>([]);
  const [listLoading, setListLoading] = useState(false);
  const [actionLoading, setActionLoading] = useState(false);
  const listRequestCoordinatorRef = useRef(createListRequestCoordinator(setListLoading));
  const [sourceModalOpen, setSourceModalOpen] = useState(false);
  const [editingSource, setEditingSource] = useState<PatchSource | null>(null);
  const [form] = Form.useForm();
  const sourceType = Form.useWatch('source_type', form);
  const [sourceSearch, setSourceSearch] = useState('');
  const [pagination, setPagination] = useState({ current: 1, pageSize: 20, total: 0 });
  const [testingConnectivity, setTestingConnectivity] = useState(false);
  const [connectivityResult, setConnectivityResult] = useState<{
    status: 'connected' | 'failed'; detail: string; checkedAt: string;
  }>();
  const { convertToLocalizedTime } = useLocalizedTime();

  const loadSources = async (page = pagination.current, pageSize = pagination.pageSize, search = sourceSearch) => {
    const coordinator = listRequestCoordinatorRef.current;
    const ticket = coordinator.begin({ visible: true });
    if (!ticket) return;
    try {
      const params: any = { page, page_size: pageSize };
      if (search.trim()) {
        params.search = search.trim();
      }
      const res = await api.getPatchSourceList(params, { signal: ticket.signal });
      if (!coordinator.shouldApply(ticket)) return;
      setSources(res.items || []);
      setPagination({ current: page, pageSize, total: res.count || 0 });
    } catch {
      if (!coordinator.shouldApply(ticket)) return;
      setSources([]);
      setPagination((prev) => ({ ...prev, total: 0 }));
    } finally {
      coordinator.finish(ticket);
    }
  };

  const handleSearchChange = (value: string) => {
    setSourceSearch(value);
    if (value === '') {
      loadSources(1, pagination.pageSize, '');
    }
  };

  useEffect(() => {
    if (authLoading || activeKey !== 'source') return;
    loadSources(1, pagination.pageSize);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [authLoading, activeKey]);

  useEffect(() => () => {
    listRequestCoordinatorRef.current.invalidate();
  }, []);

  const openSourceModal = (record?: PatchSource) => {
    setEditingSource(record || null);
    const proxyStr = record?.proxy_host ? `http://${record.proxy_host}${record.proxy_port ? ':' + record.proxy_port : ''}` : '';
    form.resetFields();
    form.setFieldsValue(record ? {
      ...record,
      proxy: proxyStr,
      auth_password: record.has_auth_password ? SAVED_SECRET : undefined,
    } : { name: '', source_type: 'wsus', url: '', proxy: '', is_enabled: true });
    setConnectivityResult(undefined);
    setSourceModalOpen(true);
  };

  const buildSourcePayload = (values: Record<string, any>) => {
    let proxyHost = '';
    let proxyPort: number | null = null;
    if (values.proxy) {
      const match = values.proxy.match(/^(?:https?:\/\/)?([^:\/\s]+)(?::(\d+))?/);
      if (match) {
        proxyHost = match[1];
        proxyPort = match[2] ? parseInt(match[2], 10) : null;
      }
    }
    const payload: Record<string, any> = { ...values, proxy_host: proxyHost, proxy_port: proxyPort };
    delete payload.proxy;
    if (payload.auth_password === SAVED_SECRET) {
      delete payload.auth_password;
    }
    return payload;
  };

  const handleSourceFormTest = async () => {
    let values: Record<string, any>;
    try {
      values = await form.validateFields();
    } catch {
      return;
    }
    setTestingConnectivity(true);
    try {
      const payload = buildSourcePayload(values);
      const result = editingSource
        ? await api.testExistingPatchSourceConnectivity(editingSource.id, payload)
        : await api.testPatchSourceConnectivity(payload);
      setConnectivityResult({
        status: result.connectivity_status === 'connected' ? 'connected' : 'failed',
        detail: result.detail,
        checkedAt: new Date().toISOString(),
      });
    } finally {
      setTestingConnectivity(false);
    }
  };

  const runConnectionTest = async (ids: number[]) => {
    if (ids.length === 0) return;
    setActionLoading(true);
    try {
      const results = await api.checkPatchSourceConnectivity(ids);
      const successCount = results.filter((r) => r.connectivity_status === 'connected').length;
      message.success(t('patchManager.settingsPage.connectivityCompleted', undefined, { success: successCount, total: results.length }));
      await loadSources();
    } catch {
    } finally {
      setActionLoading(false);
    }
  };

  const handleToggleEnabled = async (record: PatchSource, checked: boolean) => {
    setActionLoading(true);
    try {
      await api.setPatchSourceEnabled(record.id, checked);
      message.success(t(checked ? 'patchManager.settingsPage.sourceEnabled' : 'patchManager.settingsPage.sourceDisabled', undefined, { name: record.name }));
      await loadSources();
    } catch {
    } finally {
      setActionLoading(false);
    }
  };

  const handleSaveSource = async () => {
    const values = await form.validateFields();
    setActionLoading(true);
    try {
      const payload = buildSourcePayload(values);
      if (editingSource) {
        await api.updatePatchSource(editingSource.id, payload);
        message.success(t('patchManager.settingsPage.sourceUpdated', undefined, { name: values.name }));
      } else {
        if (!payload.distro_name) {
          payload.distro_name = inferDistro(values.source_type, values.url);
        }
        await api.createPatchSource(payload);
        message.success(t('patchManager.settingsPage.sourceCreated', undefined, { name: values.name }));
      }
      setSourceModalOpen(false);
      await loadSources();
    } catch {
    } finally {
      setActionLoading(false);
    }
  };

  const handleDeleteSource = async (record: PatchSource) => {
    setActionLoading(true);
    try {
      await api.deletePatchSource(record.id);
      message.success(t('patchManager.settingsPage.sourceDeleted'));
      await loadSources();
    } catch {
    } finally {
      setActionLoading(false);
    }
  };

  const cols: ColumnsType<PatchSource> = [
    { title: t('patchManager.pluginName'), dataIndex: 'name', width: 150 },
    {
      title: t('patchManager.settingsPage.type'),
      dataIndex: 'source_type',
      minWidth: 100,
      render: (_: unknown, r: PatchSource) => (
        <Tag style={{ whiteSpace: 'nowrap' }}>{r.source_type_display || r.source_type}</Tag>
      ),
    },
    { title: 'URL', dataIndex: 'url', ellipsis: true },
    {
      title: t('patchManager.settingsPage.proxy'),
      width: 140,
      render: (_: unknown, r: PatchSource) => {
        const proxy = r.proxy_host ? `http://${r.proxy_host}${r.proxy_port ? ':' + r.proxy_port : ''}` : '';
        return <span style={{ color: proxy ? 'var(--color-text-1, #1f1f1f)' : 'var(--color-text-3, #8c8c8c)' }}>{proxy || '-'}</span>;
      },
    },
    {
      title: t('patchManager.enable'),
      width: 90,
      render: (_: unknown, r: PatchSource) => <Switch size="small" checked={r.is_enabled} onChange={(checked) => handleToggleEnabled(r, checked)} />,
    },
    {
      title: t('patchManager.connectivity'),
      width: 120,
      render: (_: unknown, r: PatchSource) => (
        <span style={{ color: getConnColor(r.connectivity_status) }}>● {t(`patchManager.settingsPage.connectivity.${getConnStatusKey(r.connectivity_status)}`)}</span>
      ),
    },
    {
      title: t('patchManager.settingsPage.applicableSystem'),
      width: 180,
      ellipsis: true,
      render: (_: unknown, r: PatchSource) => r.distro_name || r.os_version || r.arch || '—',
    },
    {
      title: t('patchManager.operation'),
      width: 220,
      fixed: 'right',
      render: (_: unknown, r: PatchSource) => (
        <Space size={10}>
          <PermissionWrapper requiredPermissions={['Edit']}><a style={{ color: 'var(--color-primary, #1677ff)' }} onClick={() => openSourceModal(r)}>{t('patchManager.edit')}</a></PermissionWrapper>
          <PermissionWrapper requiredPermissions={['Edit']}><a style={{ color: 'var(--color-primary, #1677ff)' }} onClick={() => runConnectionTest([r.id])}>{t('patchManager.testConnection')}</a></PermissionWrapper>
          <PermissionWrapper requiredPermissions={['Delete']}><Popconfirm title={t('patchManager.settingsPage.confirmDeleteSource')} onConfirm={() => handleDeleteSource(r)} okText={t('patchManager.delete')} cancelText={t('patchManager.cancel')}>
            <a style={{ color: '#ff4d4f' }}>{t('patchManager.delete')}</a>
          </Popconfirm></PermissionWrapper>
        </Space>
      ),
    },
  ];

  return (
    <>
      <div style={{ display: 'flex', flexDirection: 'column', height: '100%' }}>
        <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 12, flexShrink: 0 }}>
          <Input.Search
            placeholder={t('patchManager.patchSourceName')}
            value={sourceSearch}
            onChange={(e) => handleSearchChange(e.target.value)}
            onSearch={() => loadSources(1)}
            allowClear
            style={{ width: 200 }}
          />
          <Space>
            <PermissionWrapper requiredPermissions={['Add']}><Button type="primary" icon={<PlusOutlined />} onClick={() => openSourceModal()}>{t('patchManager.settingsPage.addSource')}</Button></PermissionWrapper>
          </Space>
        </div>
        <div style={{ flex: 1, minHeight: 0 }}>
          <CustomTable
            loading={listLoading || actionLoading}
            size="middle"
            rowKey="id"
            rowSelection={{ type: 'checkbox', selectedRowKeys: selectedSources, onChange: setSelectedSources }}
            columns={cols}
            dataSource={sources}
            pagination={{
              current: pagination.current,
              pageSize: pagination.pageSize,
              total: pagination.total,
              showSizeChanger: true,
              showTotal: (total) => t('patchManager.common.totalItems', undefined, { count: total }),
              onChange: (page, pageSize) => loadSources(page, pageSize),
            }}
          />
        </div>
      </div>

      <Modal
        title={editingSource ? t('patchManager.settingsPage.editSource') : t('patchManager.settingsPage.addSource')}
        open={sourceModalOpen}
        onCancel={() => setSourceModalOpen(false)}
        footer={
          <Space style={{ width: '100%', justifyContent: 'flex-end' }}>
            <Button onClick={() => setSourceModalOpen(false)}>{t('patchManager.cancel')}</Button>
            <PermissionWrapper requiredPermissions={[editingSource ? 'Edit' : 'Add']}>
              <Button loading={testingConnectivity} onClick={handleSourceFormTest}>{t('patchManager.testConnection')}</Button>
            </PermissionWrapper>
            <PermissionWrapper requiredPermissions={[editingSource ? 'Edit' : 'Add']}>
              <Button type="primary" loading={actionLoading} onClick={handleSaveSource}>{t('patchManager.save')}</Button>
            </PermissionWrapper>
          </Space>
        }
      >
        <Form form={form} layout="vertical" style={{ marginTop: 8 }}>
          <Form.Item label={t('patchManager.pluginName')} name="name" rules={[{ required: true, message: t('patchManager.settingsPage.nameRequired') }]}>
            <Input placeholder={t('patchManager.settingsPage.namePlaceholder')} />
          </Form.Item>
          <Form.Item label={t('patchManager.settingsPage.type')} name="source_type" rules={[{ required: true, message: t('patchManager.settingsPage.typeRequired') }]}>
            <Select options={SOURCE_TYPE_OPTIONS} />
          </Form.Item>
          <Form.Item label="URL" name="url" rules={[{ required: true, message: t('patchManager.settingsPage.urlRequired') }]}>
            <Input placeholder="https://..." />
          </Form.Item>
          <Form.Item label={t('patchManager.settingsPage.proxy')} name="proxy">
            <Input placeholder={t('patchManager.settingsPage.proxyPlaceholder')} />
          </Form.Item>
          {sourceType === 'wsus' && (
            <>
              <Form.Item label={t('patchManager.authUser')} name="auth_user">
                <Input placeholder={t('patchManager.settingsPage.authUserPlaceholder')} />
              </Form.Item>
              <Form.Item label={t('patchManager.authPassword')} name="auth_password">
                <Password
                  placeholder={t('patchManager.settingsPage.authPasswordPlaceholder')}
                  clickToEdit={Boolean(editingSource?.has_auth_password)}
                />
              </Form.Item>
            </>
          )}
          {sourceType !== 'wsus' && (
            <>
              <Form.Item label={t('patchManager.settingsPage.applicableSystem')} name="distro_name" rules={[{ required: true, message: t('patchManager.settingsPage.applicableSystemRequired') }]}>
                <Input placeholder={t('patchManager.settingsPage.applicableSystemPlaceholder')} />
              </Form.Item>
              <Form.Item label={t('patchManager.osVersion')} name="os_version">
                <Input placeholder={t('patchManager.settingsPage.osVersionPlaceholder')} />
              </Form.Item>
            </>
          )}
          <Form.Item label={t('patchManager.arch')} name="arch">
            <Input placeholder={t('patchManager.settingsPage.archPlaceholder')} />
          </Form.Item>
          <Form.Item label={t('patchManager.enabled')} name="is_enabled" valuePropName="checked">
            <Switch />
          </Form.Item>
          {connectivityResult && (
            <Alert
              key={connectivityResult.checkedAt}
              closable
              showIcon
              style={{ marginBottom: 16 }}
              type={connectivityResult.status === 'connected' ? 'success' : 'error'}
              message={t(connectivityResult.status === 'connected' ? 'patchManager.settingsPage.connectivityPassed' : 'patchManager.settingsPage.connectivityFailed')}
              description={`${connectivityResult.detail} · ${convertToLocalizedTime(connectivityResult.checkedAt)}`}
            />
          )}
        </Form>
      </Modal>
    </>
  );
}

function ScanSettingTab({ activeKey }: { activeKey: string }) {
  const { t } = useTranslation();
  const api = usePatchManagerApi();
  const { isLoading: authLoading } = useApiClient();
  const [loading, setLoading] = useState(false);
  const [saving, setSaving] = useState(false);
  const [freq, setFreq] = useState<'hourly' | 'daily' | 'weekly'>('daily');
  const [hourInterval, setHourInterval] = useState(1);
  const [weekday, setWeekday] = useState(1);
  const [time, setTime] = useState<Dayjs>(dayjs('02:00', 'HH:mm'));
  const [isEnabled, setIsEnabled] = useState(true);

  const loadSettings = async () => {
    setLoading(true);
    try {
      const data = await api.getScanSetting();
      setFreq(data.frequency || 'daily');
      setHourInterval(data.hour_interval || 1);
      setWeekday(data.weekday || 1);
      setTime(dayjs(data.time || '02:00', 'HH:mm'));
      setIsEnabled(data.is_enabled !== false);
    } catch {
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    if (authLoading || activeKey !== 'scan') return;
    loadSettings();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [authLoading, activeKey]);

  const handleSave = async () => {
    setSaving(true);
    try {
      await api.updateScanSetting({
        frequency: freq,
        hour_interval: hourInterval,
        weekday,
        time: time.format('HH:mm'),
        is_enabled: isEnabled,
      });
      message.success(t('patchManager.settingsPage.scanSaved'));
    } catch {
    } finally {
      setSaving(false);
    }
  };

  const triggerText =
    freq === 'hourly'
      ? t('patchManager.settingsPage.hourlyTrigger', undefined, { count: hourInterval })
      : freq === 'daily'
        ? t('patchManager.settingsPage.dailyTrigger', undefined, { time: time.format('HH:mm') })
        : t('patchManager.settingsPage.weeklyTrigger', undefined, { weekday: t(`patchManager.settingsPage.weekday.${weekday}`), time: time.format('HH:mm') });

  const triggers = [
    { icon: <ClockCircleOutlined />, text: triggerText },
    { icon: <LinkOutlined />, text: t('patchManager.settingsPage.triggerBaselineBound') },
    { icon: <EditOutlined />, text: t('patchManager.settingsPage.triggerBaselineChanged') },
    { icon: <PlayCircleOutlined />, text: t('patchManager.settingsPage.triggerManual') },
    { icon: <CheckCircleOutlined />, text: t('patchManager.settingsPage.triggerPostRemediation') },
  ];

  return (
    <Spin spinning={loading} tip={t('patchManager.settingsPage.loading')}>
      <div>
        <div style={{ fontWeight: 500, marginBottom: 8 }}>{t('patchManager.settingsPage.globalSchedule')}</div>
        <Space style={{ marginBottom: 16, alignItems: 'flex-start' }}>
          <Select
            value={freq}
            style={{ width: 120 }}
            onChange={setFreq}
            options={['hourly', 'daily', 'weekly'].map((value) => ({ label: t(`patchManager.settingsPage.frequency.${value}`), value }))}
          />
          {freq === 'hourly' && (
            <Space>
              <span>{t('patchManager.settingsPage.every')}</span>
              <InputNumber min={1} max={24} value={hourInterval} onChange={(v) => setHourInterval(v || 1)} style={{ width: 70 }} />
              <span>{t('patchManager.settingsPage.hoursOnce')}</span>
            </Space>
          )}
          {(freq === 'daily' || freq === 'weekly') && (
            <Space>
              {freq === 'weekly' && (
                <Select value={weekday} onChange={setWeekday} style={{ width: 100 }} options={[1, 2, 3, 4, 5, 6, 7].map((value) => ({ label: t(`patchManager.settingsPage.weekday.${value}`), value }))} />
              )}
              <TimePicker value={time} format="HH:mm" onChange={(v) => v && setTime(v)} placeholder="02:00" />
            </Space>
          )}
        </Space>

        <div style={{ marginBottom: 12 }}>
          <span style={{ marginRight: 8 }}>{t('patchManager.settingsPage.enableScheduledAssessment')}</span>
          <Switch checked={isEnabled} onChange={setIsEnabled} />
        </div>

        <Alert style={{ marginBottom: 18 }} type="info" showIcon message={t('patchManager.settingsPage.scheduleHelp')} />

        <div style={{ fontWeight: 500, marginBottom: 8 }}>{t('patchManager.settingsPage.triggerTitle')}</div>
        <div style={{ background: 'var(--color-fill-1, #f4f6f9)', borderRadius: 8, padding: '4px 14px', marginBottom: 16 }}>
          {triggers.map((t, i) => (
            <div key={i} style={{ padding: '9px 0', borderBottom: i < triggers.length - 1 ? '1px solid var(--color-border-1, #e8e8e8)' : 'none', fontSize: 13 }}>
              <span style={{ color: 'var(--color-primary, #1677ff)', marginRight: 8 }}>{t.icon}</span>{t.text}
            </div>
          ))}
        </div>

        <div style={{ display: 'flex', justifyContent: 'flex-end' }}>
          <PermissionWrapper requiredPermissions={['Edit']}><Button type="primary" loading={saving} onClick={handleSave}>{t('patchManager.settingsPage.saveSettings')}</Button></PermissionWrapper>
        </div>
      </div>
    </Spin>
  );
}

export default function SettingsPage() {
  const { t } = useTranslation();
  const [activeKey, setActiveKey] = useState('source');

  return (
    <div className={styles.settingsContainer}>
      <Tabs
        activeKey={activeKey}
        onChange={setActiveKey}
        className={styles.settingsTabs}
        items={[
          { key: 'source', label: t('patchManager.patchSource'), children: <SourcesTab activeKey={activeKey} /> },
          { key: 'scan', label: t('patchManager.settingsPage.scanSettings'), children: <ScanSettingTab activeKey={activeKey} /> },
        ]}
      />
    </div>
  );
}
