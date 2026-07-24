'use client';

import React, { useState, useEffect } from 'react';
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

const SOURCE_TYPE_OPTIONS: { label: string; value: PatchSourceType }[] = [
  { label: 'WSUS', value: 'wsus' },
  { label: 'yum repo', value: 'yum_repo' },
  { label: 'dnf repo', value: 'dnf_repo' },
  { label: 'apt repo', value: 'apt_repo' },
];

const SAVED_SECRET = '********';

function formatConnStatus(status?: string) {
  if (status === 'connected') return '连通';
  if (status === 'failed') return '失败';
  return '未检测';
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
  return '未识别';
}

function SourcesTab({ activeKey }: { activeKey: string }) {
  const api = usePatchManagerApi();
  const { isLoading: authLoading } = useApiClient();
  const [selectedSources, setSelectedSources] = useState<React.Key[]>([]);
  const [sources, setSources] = useState<PatchSource[]>([]);
  const [loading, setLoading] = useState(false);
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
    setLoading(true);
    try {
      const params: any = { page, page_size: pageSize };
      if (search.trim()) {
        params.search = search.trim();
      }
      const res = await api.getPatchSourceList(params);
      setSources(res.items || []);
      setPagination({ current: page, pageSize, total: res.count || 0 });
    } catch {
      setSources([]);
      setPagination((prev) => ({ ...prev, total: 0 }));
    } finally {
      setLoading(false);
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
    setLoading(true);
    try {
      const results = await api.checkPatchSourceConnectivity(ids);
      const successCount = results.filter((r) => r.connectivity_status === 'connected').length;
      message.success(`连通性检测完成：${successCount}/${results.length} 个源连通`);
      await loadSources();
    } catch {
      setLoading(false);
    }
  };

  const handleToggleEnabled = async (record: PatchSource, checked: boolean) => {
    setLoading(true);
    try {
      await api.setPatchSourceEnabled(record.id, checked);
      message.success(`已${checked ? '启用' : '停用'}补丁源：${record.name}`);
      await loadSources();
    } catch {
      setLoading(false);
    }
  };

  const handleSaveSource = async () => {
    const values = await form.validateFields();
    setLoading(true);
    try {
      const payload = buildSourcePayload(values);
      if (editingSource) {
        await api.updatePatchSource(editingSource.id, payload);
        message.success(`已更新补丁源：${values.name}`);
      } else {
        if (!payload.distro_name) {
          payload.distro_name = inferDistro(values.source_type, values.url);
        }
        await api.createPatchSource(payload);
        message.success(`已新增补丁源：${values.name}`);
      }
      setSourceModalOpen(false);
      await loadSources();
    } catch {
    } finally {
      setLoading(false);
    }
  };

  const handleDeleteSource = async (record: PatchSource) => {
    setLoading(true);
    try {
      await api.deletePatchSource(record.id);
      message.success('已删除');
      await loadSources();
    } catch {
      setLoading(false);
    }
  };

  const cols: ColumnsType<PatchSource> = [
    { title: '名称', dataIndex: 'name', width: 150 },
    {
      title: '类型',
      dataIndex: 'source_type',
      minWidth: 100,
      render: (_: unknown, r: PatchSource) => (
        <Tag style={{ whiteSpace: 'nowrap' }}>{r.source_type_display || r.source_type}</Tag>
      ),
    },
    { title: 'URL', dataIndex: 'url', ellipsis: true },
    {
      title: '代理',
      width: 140,
      render: (_: unknown, r: PatchSource) => {
        const proxy = r.proxy_host ? `http://${r.proxy_host}${r.proxy_port ? ':' + r.proxy_port : ''}` : '';
        return <span style={{ color: proxy ? 'var(--color-text-1, #1f1f1f)' : 'var(--color-text-3, #8c8c8c)' }}>{proxy || '-'}</span>;
      },
    },
    {
      title: '启用',
      width: 90,
      render: (_: unknown, r: PatchSource) => <Switch size="small" checked={r.is_enabled} onChange={(checked) => handleToggleEnabled(r, checked)} />,
    },
    {
      title: '连通性',
      width: 120,
      render: (_: unknown, r: PatchSource) => (
        <span style={{ color: getConnColor(r.connectivity_status) }}>● {formatConnStatus(r.connectivity_status)}</span>
      ),
    },
    {
      title: '适用发行版/系统',
      width: 180,
      ellipsis: true,
      render: (_: unknown, r: PatchSource) => r.distro_name || r.os_version || r.arch || '—',
    },
    {
      title: '操作',
      width: 220,
      fixed: 'right',
      render: (_: unknown, r: PatchSource) => (
        <Space size={10}>
          <PermissionWrapper requiredPermissions={['Edit']}><a style={{ color: 'var(--color-primary, #1677ff)' }} onClick={() => openSourceModal(r)}>编辑</a></PermissionWrapper>
          <PermissionWrapper requiredPermissions={['Edit']}><a style={{ color: 'var(--color-primary, #1677ff)' }} onClick={() => runConnectionTest([r.id])}>测试连接</a></PermissionWrapper>
          <PermissionWrapper requiredPermissions={['Delete']}><Popconfirm title="确定删除该补丁源？" onConfirm={() => handleDeleteSource(r)} okText="删除" cancelText="取消">
            <a style={{ color: '#ff4d4f' }}>删除</a>
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
            placeholder="源名称"
            value={sourceSearch}
            onChange={(e) => handleSearchChange(e.target.value)}
            onSearch={() => loadSources(1)}
            allowClear
            style={{ width: 200 }}
          />
          <Space>
            <PermissionWrapper requiredPermissions={['Add']}><Button type="primary" icon={<PlusOutlined />} onClick={() => openSourceModal()}>新增补丁源</Button></PermissionWrapper>
          </Space>
        </div>
        <div style={{ flex: 1, minHeight: 0 }}>
          <CustomTable
            loading={loading}
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
              showTotal: (t) => `共 ${t} 条`,
              onChange: (page, pageSize) => loadSources(page, pageSize),
            }}
          />
        </div>
      </div>

      <Modal
        title={editingSource ? '编辑补丁源' : '新增补丁源'}
        open={sourceModalOpen}
        onCancel={() => setSourceModalOpen(false)}
        footer={
          <Space style={{ width: '100%', justifyContent: 'flex-end' }}>
            <Button onClick={() => setSourceModalOpen(false)}>取消</Button>
            <PermissionWrapper requiredPermissions={[editingSource ? 'Edit' : 'Add']}>
              <Button loading={testingConnectivity} onClick={handleSourceFormTest}>测试连通性</Button>
            </PermissionWrapper>
            <PermissionWrapper requiredPermissions={[editingSource ? 'Edit' : 'Add']}>
              <Button type="primary" loading={loading} onClick={handleSaveSource}>保存</Button>
            </PermissionWrapper>
          </Space>
        }
      >
        <Form form={form} layout="vertical" style={{ marginTop: 8 }}>
          <Form.Item label="名称" name="name" rules={[{ required: true, message: '请输入名称' }]}>
            <Input placeholder="例如：公司 WSUS" />
          </Form.Item>
          <Form.Item label="类型" name="source_type" rules={[{ required: true, message: '请选择类型' }]}>
            <Select options={SOURCE_TYPE_OPTIONS} />
          </Form.Item>
          <Form.Item label="URL" name="url" rules={[{ required: true, message: '请输入 URL' }]}>
            <Input placeholder="https://..." />
          </Form.Item>
          <Form.Item label="代理" name="proxy">
            <Input placeholder="可选，如 http://proxy.intranet:8080" />
          </Form.Item>
          {sourceType === 'wsus' && (
            <>
              <Form.Item label="认证用户名" name="auth_user">
                <Input placeholder="可选，如 DOMAIN\\svc-wsus" />
              </Form.Item>
              <Form.Item label="认证密码" name="auth_password">
                <Password
                  placeholder="请输入认证密码"
                  clickToEdit={Boolean(editingSource?.has_auth_password)}
                />
              </Form.Item>
            </>
          )}
          {sourceType !== 'wsus' && (
            <>
              <Form.Item label="适用发行版/系统" name="distro_name" rules={[{ required: true, message: '请输入适用发行版或系统' }]}> 
                <Input placeholder="如 Ubuntu / Rocky Linux" />
              </Form.Item>
              <Form.Item label="系统版本" name="os_version">
                <Input placeholder="如 22.04 / 9（apt 源必填，用于映射代号）" />
              </Form.Item>
            </>
          )}
          <Form.Item label="架构" name="arch">
            <Input placeholder="如 x86_64 / amd64（可选）" />
          </Form.Item>
          <Form.Item label="启用状态" name="is_enabled" valuePropName="checked">
            <Switch />
          </Form.Item>
          {connectivityResult && (
            <Alert
              showIcon
              style={{ marginBottom: 16 }}
              type={connectivityResult.status === 'connected' ? 'success' : 'error'}
              message={connectivityResult.status === 'connected' ? '连通性测试通过' : '连通性测试失败'}
              description={`${connectivityResult.detail} · ${convertToLocalizedTime(connectivityResult.checkedAt)}`}
            />
          )}
        </Form>
      </Modal>
    </>
  );
}

function ScanSettingTab({ activeKey }: { activeKey: string }) {
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
      message.success('扫描设置已保存');
    } catch {
    } finally {
      setSaving(false);
    }
  };

  const triggerText =
    freq === 'hourly'
      ? `全局周期到达（每 ${hourInterval} 小时）自动评估所有主机`
      : freq === 'daily'
        ? `全局周期到达（每天 ${time.format('HH:mm')}）自动评估所有主机`
        : `全局周期到达（每周${['日', '一', '二', '三', '四', '五', '六'][weekday % 7]} ${time.format('HH:mm')}）自动评估所有主机`;

  const triggers = [
    { icon: <ClockCircleOutlined />, text: triggerText },
    { icon: <LinkOutlined />, text: '主机首次绑定基线后进入待评估' },
    { icon: <EditOutlined />, text: '主机更换基线或基线补丁要求变更后重置为待评估' },
    { icon: <PlayCircleOutlined />, text: '页面点击「立即评估」立即执行' },
    { icon: <CheckCircleOutlined />, text: '安装或重启完成后自动验证' },
  ];

  return (
    <Spin spinning={loading} tip="加载中...">
      <div>
        <div style={{ fontWeight: 500, marginBottom: 8 }}>全局评估周期</div>
        <Space style={{ marginBottom: 16, alignItems: 'flex-start' }}>
          <Select
            value={freq}
            style={{ width: 120 }}
            onChange={setFreq}
            options={[{ label: '每小时', value: 'hourly' }, { label: '每天', value: 'daily' }, { label: '每周', value: 'weekly' }]}
          />
          {freq === 'hourly' && (
            <Space>
              <span>每</span>
              <InputNumber min={1} max={24} value={hourInterval} onChange={(v) => setHourInterval(v || 1)} style={{ width: 70 }} />
              <span>小时执行一次</span>
            </Space>
          )}
          {(freq === 'daily' || freq === 'weekly') && (
            <Space>
              {freq === 'weekly' && (
                <Select value={weekday} onChange={setWeekday} style={{ width: 100 }} options={[{ label: '周一', value: 1 }, { label: '周二', value: 2 }, { label: '周三', value: 3 }, { label: '周四', value: 4 }, { label: '周五', value: 5 }, { label: '周六', value: 6 }, { label: '周日', value: 7 }]} />
              )}
              <TimePicker value={time} format="HH:mm" onChange={(v) => v && setTime(v)} placeholder="02:00" />
            </Space>
          )}
        </Space>

        <div style={{ marginBottom: 12 }}>
          <span style={{ marginRight: 8 }}>启用周期评估</span>
          <Switch checked={isEnabled} onChange={setIsEnabled} />
        </div>

        <Alert style={{ marginBottom: 18 }} type="info" showIcon message="启用后系统将按周期自动评估所有主机合规状态。关闭后不会自动创建周期评估任务，手动评估不受影响。" />

        <div style={{ fontWeight: 500, marginBottom: 8 }}>什么时候会触发评估</div>
        <div style={{ background: 'var(--color-fill-1, #f4f6f9)', borderRadius: 8, padding: '4px 14px', marginBottom: 16 }}>
          {triggers.map((t, i) => (
            <div key={i} style={{ padding: '9px 0', borderBottom: i < triggers.length - 1 ? '1px solid var(--color-border-1, #e8e8e8)' : 'none', fontSize: 13 }}>
              <span style={{ color: 'var(--color-primary, #1677ff)', marginRight: 8 }}>{t.icon}</span>{t.text}
            </div>
          ))}
        </div>

        <div style={{ display: 'flex', justifyContent: 'flex-end' }}>
          <PermissionWrapper requiredPermissions={['Edit']}><Button type="primary" loading={saving} onClick={handleSave}>保存设置</Button></PermissionWrapper>
        </div>
      </div>
    </Spin>
  );
}

export default function SettingsPage() {
  const [activeKey, setActiveKey] = useState('source');

  return (
    <div className={styles.settingsContainer}>
      <Tabs
        activeKey={activeKey}
        onChange={setActiveKey}
        className={styles.settingsTabs}
        items={[
          { key: 'source', label: '补丁源', children: <SourcesTab activeKey={activeKey} /> },
          { key: 'scan', label: '扫描设置', children: <ScanSettingTab activeKey={activeKey} /> },
        ]}
      />
    </div>
  );
}
