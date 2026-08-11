'use client';

import React, { useState, useEffect, useRef } from 'react';
import { Tag, Button, Tabs, Input, Select, Space, TimePicker, Alert, message, Form, Switch, Modal, InputNumber, Spin, Tooltip } from 'antd';
import PermissionWrapper from '@/components/permission';
import PatchDeletePopconfirm from '@/app/patch-manager/components/delete-popconfirm';
import Password from '@/components/password';
import SourceOriginBadge from '@/components/source-origin-badge';
import NotificationRuleMatrix from '@/app/patch-manager/components/notification-rule-matrix';
import type { Dayjs } from 'dayjs';
import dayjs from 'dayjs';
import { PlusOutlined, ClockCircleOutlined, LinkOutlined, EditOutlined, PlayCircleOutlined, CheckCircleOutlined } from '@ant-design/icons';
import CustomTable from '@/components/custom-table';
import type { ColumnsType } from 'antd/es/table';
import SearchActionBar from '@/components/search-action-bar';
import useApiClient from '@/utils/request';
import usePatchManagerApi from '@/app/patch-manager/api';
import type {
  NoticeChannel,
  NoticeRuleDraft,
  NoticeUser,
  PatchSource,
  PatchSourceType,
} from '@/app/patch-manager/types';
import styles from './page.module.scss';
import { useLocalizedTime } from '@/hooks/useLocalizedTime';
import { useTranslation } from '@/utils/i18n';
import { createListRequestCoordinator } from '@/app/patch-manager/utils/list-request-coordinator';
import {
  formatSourceApplicableScope,
  LINUX_ARCHITECTURE_OPTIONS,
  normalizeArchitecture,
} from '@/app/patch-manager/constants/architecture';

const SOURCE_TYPE_OPTIONS: { label: string; value: PatchSourceType }[] = [
  { label: 'WSUS', value: 'wsus' },
  { label: 'yum repo', value: 'yum_repo' },
  { label: 'dnf repo', value: 'dnf_repo' },
  { label: 'apt repo', value: 'apt_repo' },
];

const SOURCE_URL_TEXT_KEYS: Record<PatchSourceType, { label: string; help: string; placeholder: string }> = {
  wsus: {
    label: 'patchManager.catalogUrl',
    help: 'patchManager.settingsPage.wsusUrlHelp',
    placeholder: 'patchManager.settingsPage.wsusUrlPlaceholder',
  },
  yum_repo: {
    label: 'patchManager.repoUrl',
    help: 'patchManager.settingsPage.yumRepoUrlHelp',
    placeholder: 'patchManager.settingsPage.yumRepoUrlPlaceholder',
  },
  dnf_repo: {
    label: 'patchManager.repoUrl',
    help: 'patchManager.settingsPage.dnfRepoUrlHelp',
    placeholder: 'patchManager.settingsPage.dnfRepoUrlPlaceholder',
  },
  apt_repo: {
    label: 'patchManager.repoUrl',
    help: 'patchManager.settingsPage.aptRepoUrlHelp',
    placeholder: 'patchManager.settingsPage.aptRepoUrlPlaceholder',
  },
};

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
  const sourceType = (Form.useWatch('source_type', form) || 'wsus') as PatchSourceType;
  const sourceUrlTextKeys = SOURCE_URL_TEXT_KEYS[sourceType];
  const sourceUrlLabel = t(sourceUrlTextKeys.label);
  const sourceUrlHelp = t(sourceUrlTextKeys.help);
  const sourceUrlPlaceholder = t(sourceUrlTextKeys.placeholder);
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
      arch: normalizeArchitecture(record.arch),
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
    if (payload.source_type === 'wsus') delete payload.arch;
    if (
      payload.auth_password === SAVED_SECRET
      || (editingSource?.has_auth_password && !payload.auth_password)
    ) {
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
    {
      title: t('patchManager.pluginName'),
      dataIndex: 'name',
      width: 220,
    },
    {
      title: t('patchManager.builtin'),
      dataIndex: 'is_builtin',
      width: 88,
      align: 'center',
      render: (isBuiltin: boolean) => isBuiltin
        ? <SourceOriginBadge kind="builtin" label={t('patchManager.yes')} />
        : <span style={{ color: 'var(--color-text-3, #8c8c8c)' }}>{t('patchManager.no')}</span>,
    },
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
      render: (_: unknown, r: PatchSource) => (
        <PermissionWrapper requiredPermissions={['Edit']}>
          <Switch
            size="small"
            checked={r.is_enabled}
            onChange={(checked) => handleToggleEnabled(r, checked)}
          />
        </PermissionWrapper>
      ),
    },
    {
      title: t('patchManager.connectivity'),
      width: 120,
      render: (_: unknown, r: PatchSource) => (
        <span style={{ color: getConnColor(r.connectivity_status) }}>● {t(`patchManager.settingsPage.connectivity.${getConnStatusKey(r.connectivity_status)}`)}</span>
      ),
    },
    {
      title: t('patchManager.settingsPage.applicableScope'),
      width: 220,
      ellipsis: true,
      render: (_: unknown, r: PatchSource) => formatSourceApplicableScope(
        r,
        t('patchManager.settingsPage.wsusApplicableScope'),
      ),
    },
    {
      title: t('patchManager.operation'),
      width: 220,
      fixed: 'right',
      render: (_: unknown, r: PatchSource) => (
        <Space size={10}>
          <PermissionWrapper requiredPermissions={['Edit']}><a style={{ color: 'var(--color-primary, #1677ff)' }} onClick={() => openSourceModal(r)}>{t('patchManager.edit')}</a></PermissionWrapper>
          <PermissionWrapper requiredPermissions={['Edit']}><a style={{ color: 'var(--color-primary, #1677ff)' }} onClick={() => runConnectionTest([r.id])}>{t('patchManager.testConnection')}</a></PermissionWrapper>
          {r.is_builtin ? (
            <Tooltip title={t('patchManager.settingsPage.builtinDeleteDisabled')}>
              <span>
                <Button type="link" danger disabled size="small" style={{ padding: 0, height: 'auto' }}>
                  {t('patchManager.delete')}
                </Button>
              </span>
            </Tooltip>
          ) : (
            <PermissionWrapper requiredPermissions={['Delete']}><PatchDeletePopconfirm title={t('patchManager.settingsPage.confirmDeleteSource', undefined, { name: r.name })} description={t('patchManager.settingsPage.deleteSourceDescription')} onConfirm={() => handleDeleteSource(r)} okText={t('patchManager.delete')} cancelText={t('patchManager.cancel')} okButtonProps={{ danger: true }}>
              <a style={{ color: '#ff4d4f' }}>{t('patchManager.delete')}</a>
            </PatchDeletePopconfirm></PermissionWrapper>
          )}
        </Space>
      ),
    },
  ];

  return (
    <>
      <div style={{ display: 'flex', flexDirection: 'column', height: '100%' }}>
        <SearchActionBar
          className='mb-[12px]'
          spacing="default"
          searchClassName="!w-[200px]"
          searchProps={{
            placeholder: t('patchManager.patchSourceName'),
            value: sourceSearch,
            onChange: (e) => handleSearchChange(e.target.value),
            onSearch: () => loadSources(1),
            allowClear: true,
          }}
          actions={(
            <PermissionWrapper requiredPermissions={['Add']}>
              <Button type="primary" icon={<PlusOutlined />} onClick={() => openSourceModal()}>
                {t('patchManager.settingsPage.addSource')}
              </Button>
            </PermissionWrapper>
          )}
        />
        <div style={{ flex: 1, minHeight: 0 }}>
          <CustomTable
            loading={listLoading || actionLoading}
            size="middle"
            rowKey="id"
            rowSelection={{
              type: 'checkbox',
              selectedRowKeys: selectedSources,
              onChange: setSelectedSources,
            }}
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
        styles={{ body: { maxHeight: 'calc(100vh - 240px)', overflowY: 'auto' } }}
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
          <Form.Item
            label={sourceUrlLabel}
            name="url"
            tooltip={sourceUrlHelp}
            rules={[{ required: true, message: t('patchManager.settingsPage.urlRequired') }]}
          >
            <Input placeholder={sourceUrlPlaceholder} />
          </Form.Item>
          <Form.Item label={t('patchManager.settingsPage.proxy')} name="proxy">
            <Input placeholder={t('patchManager.settingsPage.proxyPlaceholder')} />
          </Form.Item>
          {sourceType === 'wsus' && (
            <>
              <Form.Item
                label={t('patchManager.authUser')}
                name="auth_user"
                rules={[{ required: true, message: t('patchManager.settingsPage.authUserRequired') }]}
              >
                <Input placeholder={t('patchManager.settingsPage.authUserPlaceholder')} />
              </Form.Item>
              <Form.Item
                label={t('patchManager.authPassword')}
                name="auth_password"
                rules={[{ required: true, message: t('patchManager.settingsPage.authPasswordRequired') }]}
              >
                <Password
                  placeholder={t('patchManager.settingsPage.authPasswordPlaceholder')}
                  clickToEdit={Boolean(editingSource?.has_auth_password)}
                />
              </Form.Item>
            </>
          )}
          {sourceType !== 'wsus' && (
            <>
              <Form.Item label={t('patchManager.distro')} name="distro_name" rules={[{ required: true, message: t('patchManager.settingsPage.distroRequired') }]}>
                <Input placeholder={t('patchManager.settingsPage.distroPlaceholder')} />
              </Form.Item>
              <Form.Item label={t('patchManager.osVersion')} name="os_version">
                <Input placeholder={t('patchManager.settingsPage.osVersionPlaceholder')} />
              </Form.Item>
              <Form.Item
                label={t('patchManager.arch')}
                name="arch"
                rules={[{ required: true, message: t('patchManager.libraryPage.archRequired') }]}
              >
                <Select
                  placeholder={t('patchManager.settingsPage.archPlaceholder')}
                  options={LINUX_ARCHITECTURE_OPTIONS}
                />
              </Form.Item>
            </>
          )}
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
  const [scheduleForm] = Form.useForm<{
    frequency: 'hourly' | 'daily' | 'weekly';
    hour_interval: number;
    weekday: number;
    time: Dayjs;
  }>();
  const [loading, setLoading] = useState(false);
  const [saving, setSaving] = useState(false);
  const [isEnabled, setIsEnabled] = useState(true);
  const [notificationEnabled, setNotificationEnabled] = useState(false);
  const [notificationRules, setNotificationRules] = useState<NoticeRuleDraft[]>([]);
  const [noticeChannels, setNoticeChannels] = useState<NoticeChannel[]>([]);
  const [noticeUsers, setNoticeUsers] = useState<NoticeUser[]>([]);
  const [noticeCandidatesLoading, setNoticeCandidatesLoading] = useState(false);
  const [notificationValidationRequested, setNotificationValidationRequested] = useState(false);
  const freq = Form.useWatch('frequency', scheduleForm) || 'daily';
  const hourInterval = Form.useWatch('hour_interval', scheduleForm) ?? 1;
  const weekday = Form.useWatch('weekday', scheduleForm) ?? 1;
  const time = Form.useWatch('time', scheduleForm);

  const loadSettings = async () => {
    setLoading(true);
    try {
      const data = await api.getScanSetting();
      scheduleForm.setFieldsValue({
        frequency: data.frequency || 'daily',
        hour_interval: data.hour_interval || 1,
        weekday: data.weekday || 1,
        time: dayjs(data.time || '02:00', 'HH:mm'),
      });
      setIsEnabled(data.is_enabled !== false);
      setNotificationEnabled(data.notification_enabled === true);
      setNotificationRules((data.notification_rules || []).map((rule, index) => ({
        key: `saved-notice-rule-${rule.channel_id}-${index}`,
        channel_id: rule.channel_id,
        receivers: rule.receivers || [],
      })));
    } catch {
    } finally {
      setLoading(false);
    }

    setNoticeCandidatesLoading(true);
    try {
      const candidates = await api.getScanNotificationCandidates();
      setNoticeChannels(candidates.channels || []);
      setNoticeUsers(candidates.users || []);
    } catch {
      setNoticeChannels([]);
      setNoticeUsers([]);
    } finally {
      setNoticeCandidatesLoading(false);
    }
  };

  useEffect(() => {
    if (authLoading || activeKey !== 'scan') return;
    loadSettings();
  }, [authLoading, activeKey]);

  const handleSave = async () => {
    let scheduleValues = scheduleForm.getFieldsValue();
    if (isEnabled) {
      try {
        scheduleValues = await scheduleForm.validateFields();
      } catch {
        return;
      }
    }

    setNotificationValidationRequested(true);
    if (!isNotificationConfigurationValid) {
      message.error(t('patchManager.settingsPage.noticeConfigurationIncomplete'));
      return;
    }
    setSaving(true);
    try {
      const saved = await api.updateScanSetting({
        frequency: scheduleValues.frequency || 'daily',
        hour_interval: scheduleValues.hour_interval || 1,
        weekday: scheduleValues.weekday || 1,
        time: scheduleValues.time?.format('HH:mm') || '02:00',
        is_enabled: isEnabled,
        notification_enabled: notificationEnabled,
        notification_rules: notificationRules.map((rule) => ({
          channel_id: rule.channel_id!,
          receivers: rule.receivers,
        })),
      });
      setNotificationEnabled(saved.notification_enabled === true);
      setNotificationRules((saved.notification_rules || []).map((rule, index) => ({
        key: `saved-notice-rule-${rule.channel_id}-${index}`,
        channel_id: rule.channel_id,
        receivers: rule.receivers || [],
      })));
      setNotificationValidationRequested(false);
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
        ? t('patchManager.settingsPage.dailyTrigger', undefined, { time: time?.format('HH:mm') || '--:--' })
        : t('patchManager.settingsPage.weeklyTrigger', undefined, { weekday: t(`patchManager.settingsPage.weekday.${weekday}`), time: time?.format('HH:mm') || '--:--' });

  const triggers = [
    { icon: <ClockCircleOutlined />, text: triggerText },
    { icon: <LinkOutlined />, text: t('patchManager.settingsPage.triggerBaselineBound') },
    { icon: <EditOutlined />, text: t('patchManager.settingsPage.triggerBaselineChanged') },
    { icon: <PlayCircleOutlined />, text: t('patchManager.settingsPage.triggerManual') },
    { icon: <CheckCircleOutlined />, text: t('patchManager.settingsPage.triggerPostRemediation') },
  ];

  const isNotificationConfigurationValid = !isEnabled || !notificationEnabled || (
    notificationRules.length > 0
    && notificationRules.every((rule) => {
      if (rule.channel_id === undefined) return false;
      const channel = noticeChannels.find((item) => item.id === rule.channel_id);
      if (!channel) return false;
      return channel.channel_type === 'nats' || rule.receivers.length > 0;
    })
  );

  return (
    <Spin spinning={loading} tip={t('patchManager.settingsPage.loading')}>
      <div>
        <div className={styles.assessmentAutomationControl}>
          <div className={styles.assessmentAutomationHeader}>
            <span className={styles.assessmentAutomationTitle}>
              {t('patchManager.settingsPage.enableScheduledAssessment')}
            </span>
            <Switch
              checked={isEnabled}
              aria-label={t('patchManager.settingsPage.enableScheduledAssessment')}
              onChange={setIsEnabled}
            />
          </div>
          <Alert type="info" showIcon message={t('patchManager.settingsPage.scheduleHelp')} />
        </div>

        {isEnabled && (
          <div className={styles.assessmentAutomationPanel}>
            <div className={styles.assessmentScheduleSection}>
              <div className={styles.requiredSectionTitle}>
                {t('patchManager.settingsPage.globalSchedule')}
                <span aria-hidden="true">*</span>
              </div>
              <Form
                form={scheduleForm}
                layout="inline"
                className={styles.assessmentScheduleForm}
                initialValues={{
                  frequency: 'daily',
                  hour_interval: 1,
                  weekday: 1,
                  time: dayjs('02:00', 'HH:mm'),
                }}
              >
                <Form.Item
                  name="frequency"
                  rules={[{ required: true, message: t('patchManager.settingsPage.frequencyRequired') }]}
                >
                  <Select
                    style={{ width: 120 }}
                    options={['hourly', 'daily', 'weekly'].map((value) => ({
                      label: t(`patchManager.settingsPage.frequency.${value}`),
                      value,
                    }))}
                  />
                </Form.Item>
                {freq === 'hourly' && (
                  <>
                    <span className={styles.scheduleAffix}>{t('patchManager.settingsPage.every')}</span>
                    <Form.Item
                      name="hour_interval"
                      rules={[
                        { required: true, message: t('patchManager.settingsPage.hourIntervalRequired') },
                        { type: 'number', min: 1, max: 24, message: t('patchManager.settingsPage.hourIntervalRange') },
                      ]}
                    >
                      <InputNumber min={1} max={24} style={{ width: 70 }} />
                    </Form.Item>
                    <span className={styles.scheduleAffix}>{t('patchManager.settingsPage.hoursOnce')}</span>
                  </>
                )}
                {(freq === 'daily' || freq === 'weekly') && (
                  <>
                    {freq === 'weekly' && (
                      <Form.Item
                        name="weekday"
                        rules={[{ required: true, message: t('patchManager.settingsPage.weekdayRequired') }]}
                      >
                        <Select
                          style={{ width: 100 }}
                          options={[1, 2, 3, 4, 5, 6, 7].map((value) => ({
                            label: t(`patchManager.settingsPage.weekday.${value}`),
                            value,
                          }))}
                        />
                      </Form.Item>
                    )}
                    <Form.Item
                      name="time"
                      rules={[{ required: true, message: t('patchManager.settingsPage.assessmentTimeRequired') }]}
                    >
                      <TimePicker format="HH:mm" placeholder="02:00" />
                    </Form.Item>
                  </>
                )}
              </Form>
            </div>

            <NotificationRuleMatrix
              scheduleEnabled={isEnabled}
              notificationEnabled={notificationEnabled}
              rules={notificationRules}
              channels={noticeChannels}
              users={noticeUsers}
              loading={noticeCandidatesLoading}
              showValidationErrors={notificationValidationRequested}
              onNotificationEnabledChange={(enabled) => {
                setNotificationEnabled(enabled);
                if (!enabled) setNotificationValidationRequested(false);
              }}
              onRulesChange={setNotificationRules}
            />
          </div>
        )}

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
        className={`${styles.settingsTabs} ${activeKey === 'scan' ? styles.scanSettingsTabs : ''}`}
        items={[
          { key: 'source', label: t('patchManager.patchSource'), children: <SourcesTab activeKey={activeKey} /> },
          { key: 'scan', label: t('patchManager.settingsPage.scanSettings'), children: <ScanSettingTab activeKey={activeKey} /> },
        ]}
      />
    </div>
  );
}
