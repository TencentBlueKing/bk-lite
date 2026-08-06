'use client';

import React, { useState, useRef, useEffect, useMemo } from 'react';
import { Table, Tag, Button, Input, Space, Form, Select, Alert, Tooltip, message, Popconfirm, Spin, Modal } from 'antd';
import PermissionWrapper from '@/components/permission';
import TimeSelector from '@/components/time-selector';
import { PlusOutlined } from '@ant-design/icons';
import useApiClient from '@/utils/request';
import usePatchManagerApi from '@/app/patch-manager/api';
import DualSelector from '@/app/patch-manager/components/dual-selector';
import SeverityTag from '@/app/patch-manager/components/severity-tag';
import CustomTable from '@/components/custom-table';
import OperateDrawer from '@/app/patch-manager/components/operate-drawer';
import { useRouter } from 'next/navigation';
import { useLocalizedTime } from '@/hooks/useLocalizedTime';
import { useTranslation } from '@/utils/i18n';
import { createListRequestCoordinator } from '@/app/patch-manager/utils/list-request-coordinator';
import {
  createPatchManagerPollFrequencyOptions,
  PATCH_MANAGER_MANUAL_POLL_INTERVAL_MS,
} from '@/app/patch-manager/constants/polling';
import {
  formatArchitectures,
  normalizeArchitectures,
} from '@/app/patch-manager/constants/architecture';

export default function BaselineManagementPage() {
  const { t } = useTranslation();
  const router = useRouter();
  const { convertToLocalizedTime } = useLocalizedTime();
  const api = usePatchManagerApi();
  const { isLoading } = useApiClient();
  const [data, setData] = useState<any[]>([]);
  const [listLoading, setListLoading] = useState(false);
  const [saving, setSaving] = useState(false);
  const [bindSaving, setBindSaving] = useState(false);
  const [editOpen, setEditOpen] = useState(false);
  const [bindOpen, setBindOpen] = useState(false);
  const [patchPickerOpen, setPatchPickerOpen] = useState(false);
  const [editing, setEditing] = useState<any | null>(null);
  const [draftOs, setDraftOs] = useState<'win' | 'linux'>('win');
  const [pickerSelected, setPickerSelected] = useState<React.Key[]>([]);
  const [requirements, setRequirements] = useState<any[]>([]);
  const [originalRequirements, setOriginalRequirements] = useState<any[]>([]);
  const [patchList, setPatchList] = useState<any[]>([]);
  const patchCacheRef = useRef<Map<number, any>>(new Map());
  const [bindTarget, setBindTarget] = useState<any | null>(null);
  const [selectedHosts, setSelectedHosts] = useState<React.Key[]>([]);
  const [originalSelectedHosts, setOriginalSelectedHosts] = useState<React.Key[]>([]);
  const [hostSearch, setHostSearch] = useState('');
  const [bindHostList, setBindHostList] = useState<any[]>([]);
  const [bindHostPagination, setBindHostPagination] = useState({ current: 1, pageSize: 20, total: 0 });
  const hostCacheRef = useRef<Map<number, any>>(new Map());
  const [baselineSearch, setBaselineSearch] = useState('');
  const [patchSearch, setPatchSearch] = useState('');
  const [patchPickerPagination, setPatchPickerPagination] = useState({ current: 1, pageSize: 20, total: 0 });
  const [patchPickerLoading, setPatchPickerLoading] = useState(false);
  const [form] = Form.useForm();
  const [bindDrawerLoading, setBindDrawerLoading] = useState(false);
  const [reqLoading, setReqLoading] = useState(false);
  const [pollIntervalMs, setPollIntervalMs] = useState(PATCH_MANAGER_MANUAL_POLL_INTERVAL_MS);
  const [pagination, setPagination] = useState({ current: 1, pageSize: 20, total: 0 });
  const baselineRequestCoordinatorRef = useRef(createListRequestCoordinator(setListLoading));
  const requirementsRequestCoordinatorRef = useRef(createListRequestCoordinator(setReqLoading));
  const patchPickerRequestCoordinatorRef = useRef(createListRequestCoordinator(setPatchPickerLoading));
  const bindHostRequestCoordinatorRef = useRef(createListRequestCoordinator(setBindDrawerLoading));
  const pollFrequencyOptions = useMemo(
    () => createPatchManagerPollFrequencyOptions(t('common.timeSelector.off')),
    [t],
  );

  const confirmInvalidateAssessment = (baselineName: string) => new Promise<boolean>((resolve) => {
    Modal.confirm({
      title: t('patchManager.baseline.invalidateTitle'),
      content: t('patchManager.baseline.invalidateContent', undefined, { name: baselineName }),
      okText: t('patchManager.baseline.continueEditing'),
      cancelText: t('patchManager.cancel'),
      onOk: () => resolve(true),
      onCancel: () => resolve(false),
    });
  });

  const loadData = async (
    page = pagination.current,
    pageSize = pagination.pageSize,
    search = baselineSearch,
    silent = false,
  ) => {
    const ticket = baselineRequestCoordinatorRef.current.begin({ visible: !silent });
    if (!ticket) return;
    try {
      const res = await api.getBaselineList(
        { page, page_size: pageSize, search: search || undefined },
        { signal: ticket.signal },
      );
      if (!baselineRequestCoordinatorRef.current.shouldApply(ticket)) return;
      setData(res.items || []);
      setPagination((p) => ({ ...p, current: page, pageSize, total: res.count || 0 }));
    } catch {
      if (
        ticket.signal.aborted
        || !baselineRequestCoordinatorRef.current.shouldApply(ticket)
      ) return;
      setData([]);
      setPagination((p) => ({ ...p, current: page, pageSize, total: 0 }));
    } finally {
      baselineRequestCoordinatorRef.current.finish(ticket);
    }
  };

  useEffect(() => {
    if (isLoading) return;
    loadData(1, pagination.pageSize);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [isLoading]);

  const baselinePollRef = useRef<() => void>(() => {});
  baselinePollRef.current = () => loadData(
    pagination.current,
    pagination.pageSize,
    baselineSearch,
    true,
  );
  useEffect(() => {
    if (isLoading || pollIntervalMs <= 0) return;
    const timer = window.setInterval(() => {
      if (!document.hidden) baselinePollRef.current();
    }, pollIntervalMs);
    return () => window.clearInterval(timer);
  }, [isLoading, pollIntervalMs]);

  useEffect(() => () => {
    baselineRequestCoordinatorRef.current.invalidate();
  }, []);

  useEffect(() => {
    if (!editOpen) {
      setReqLoading(false);
      return;
    }
    if (!editing) {
      setRequirements([]);
      setOriginalRequirements([]);
      setReqLoading(false);
      return;
    }
    const ticket = requirementsRequestCoordinatorRef.current.begin({ visible: true });
    if (!ticket) return;
    void api.getBaselineRequirements(editing.id, { signal: ticket.signal }).then((reqs) => {
      if (!requirementsRequestCoordinatorRef.current.shouldApply(ticket)) return;
      const nextRequirements = reqs || [];
      setRequirements(nextRequirements);
      setOriginalRequirements(nextRequirements);
    }).catch(() => {
      if (!requirementsRequestCoordinatorRef.current.shouldApply(ticket)) return;
      setRequirements([]);
      setOriginalRequirements([]);
    }).finally(() => {
      requirementsRequestCoordinatorRef.current.finish(ticket);
    });
    return () => {
      requirementsRequestCoordinatorRef.current.cancel(ticket);
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [editOpen, editing]);

  useEffect(() => {
    if (!patchPickerOpen) return;
    const existingIds = requirements.map((r) => r.patch);
    setPickerSelected(existingIds);
    patchCacheRef.current = new Map();
    setPatchSearch('');
    setPatchPickerPagination((p) => ({ ...p, current: 1 }));
    loadPatches(1, patchPickerPagination.pageSize, '');
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [patchPickerOpen]);

  const loadPatches = async (
    page = patchPickerPagination.current,
    pageSize = patchPickerPagination.pageSize,
    name = patchSearch,
  ) => {
    const coordinator = patchPickerRequestCoordinatorRef.current;
    const ticket = coordinator.begin({ visible: true });
    if (!ticket) return;
    try {
      const res = await api.getPatchList(
        {
          page,
          page_size: pageSize,
          os_type: draftOs === 'win' ? 'windows' : 'linux',
          pkg_status: 'ready',
          name: name || undefined,
        },
        { signal: ticket.signal },
      );
      if (!coordinator.shouldApply(ticket)) return;
      setPatchList(res.items || []);
      (res.items || []).forEach((p: any) => patchCacheRef.current.set(p.id, p));
      setPatchPickerPagination((p) => ({ ...p, current: page, pageSize, total: res.count || 0 }));
    } catch {
      if (!coordinator.shouldApply(ticket)) return;
      setPatchList([]);
      setPatchPickerPagination((p) => ({ ...p, current: page, pageSize, total: 0 }));
    } finally {
      coordinator.finish(ticket);
    }
  };

  const loadBindHosts = async (page = 1, pageSize = 20, search = hostSearch) => {
    if (!bindTarget) return;
    const coordinator = bindHostRequestCoordinatorRef.current;
    const ticket = coordinator.begin({ visible: true });
    if (!ticket) return;
    try {
      const res = await api.getPatchTargetList({
        page,
        page_size: pageSize,
        os_type: bindTarget.os_type,
        search: search || undefined,
      }, { signal: ticket.signal });
      if (!coordinator.shouldApply(ticket)) return;
      setBindHostList(res.items || []);
      setBindHostPagination({ current: page, pageSize, total: res.count || 0 });
      (res.items || []).forEach((h: any) => hostCacheRef.current.set(h.id, h));
    } catch {
      if (!coordinator.shouldApply(ticket)) return;
      setBindHostList([]);
      setBindHostPagination({ current: page, pageSize, total: 0 });
    } finally {
      coordinator.finish(ticket);
    }
  };

  const closeBindDrawer = () => {
    setBindOpen(false);
    bindHostRequestCoordinatorRef.current.invalidate();
  };

  const closePatchPicker = () => {
    setPatchPickerOpen(false);
    patchPickerRequestCoordinatorRef.current.invalidate();
  };

  const columns = [
    { title: t('patchManager.baseline.name'), dataIndex: 'name', width: 170 },
    { title: t('patchManager.osType'), dataIndex: 'os_type', width: 100, render: (v: string) => t(`patchManager.${v === 'windows' ? 'windows' : 'linux'}`) },
    { title: t('patchManager.baseline.boundTargets'), dataIndex: 'bound_host_count', width: 90, render: (v: number) => t('patchManager.dashboard.targetCount', undefined, { count: v || 0 }) },
    {
      title: t('patchManager.baseline.complianceDistribution'),
      dataIndex: 'compliance_distribution',
      width: 280,
      render: (dist: any[], r: any) => {
        const items = dist || [];
        if (!items.length) {
          return r.bound_host_count ? '—' : <span style={{ color: 'var(--color-text-4, #bfbfbf)' }}>{t('patchManager.baseline.unbound')}</span>;
        }
        return (
          <Space size={6}>
            {items.map((item: any) => (
              <Tag
                key={item.filter}
                color={item.color}
                style={{ cursor: 'pointer' }}
                onClick={() => router.push(`/patch-manager/target?baseline_id=${r.id}&compliance_status=${item.filter}`)}
              >
                {t(`patchManager.complianceStatus.${item.filter}`, item.label)} {item.count}
              </Tag>
            ))}
          </Space>
        );
      },
    },
    { title: t('patchManager.updateTime'), dataIndex: 'updated_at', width: 180, render: (v: string | null) => convertToLocalizedTime(v) || '—' },
    {
      title: t('patchManager.operation'),
      dataIndex: 'op',
      width: 250,
      render: (_: unknown, r: any) => {
        const deleteBlocked = (r.bound_host_count || 0) > 0;
        const deleteTip = deleteBlocked ? t('patchManager.baseline.deleteBlocked') : '';
        const editEl = <PermissionWrapper requiredPermissions={['Edit']}><Button type="link" size="small" onClick={() => { setEditing(r); setDraftOs(r.os_type === 'windows' ? 'win' : 'linux'); form.setFieldsValue({ name: r.name, description: r.description }); setEditOpen(true); }}>{t('patchManager.edit')}</Button></PermissionWrapper>;
        const bindEl = <PermissionWrapper requiredPermissions={['Edit']} permissionPath="/patch-manager/target"><Button type="link" size="small" onClick={async () => {
          setBindTarget(r);
          setSelectedHosts([]);
          setOriginalSelectedHosts([]);
          setHostSearch('');
          setBindOpen(true);
          hostCacheRef.current = new Map();
          setBindHostPagination({ current: 1, pageSize: 20, total: 0 });
          const coordinator = bindHostRequestCoordinatorRef.current;
          const ticket = coordinator.begin({ visible: true });
          if (!ticket) return;
          try {
            const [hostsRes, bindings] = await Promise.all([
              api.getPatchTargetList(
                { page: 1, page_size: 20, os_type: r.os_type },
                { signal: ticket.signal },
              ),
              api.getBaselineHosts(r.id, { signal: ticket.signal }),
            ]);
            if (!coordinator.shouldApply(ticket)) return;
            setBindHostList(hostsRes.items || []);
            setBindHostPagination({ current: 1, pageSize: 20, total: hostsRes.count || 0 });
            (hostsRes.items || []).forEach((h: any) => hostCacheRef.current.set(h.id, h));
            (bindings || []).forEach((b: any) => {
              if (!hostCacheRef.current.has(b.target)) {
                hostCacheRef.current.set(b.target, {
                  id: b.target,
                  name: b.target_name,
                  ip: b.target_ip,
                  os_type_display: r.os_type === 'windows' ? 'Windows' : 'Linux',
                  permission: b.permission,
                });
              }
            });
            const bindingTargetIds = (bindings || []).map((i: any) => i.target);
            setSelectedHosts(bindingTargetIds);
            setOriginalSelectedHosts(bindingTargetIds);
          } catch {
            if (!coordinator.shouldApply(ticket)) return;
            setBindHostList([]);
          } finally {
            coordinator.finish(ticket);
          }
        }}>{t('patchManager.baseline.bindTargets')}</Button></PermissionWrapper>;
        const deleteEl = deleteBlocked
          ? <Button type="link" size="small" danger disabled>{t('patchManager.delete')}</Button>
          : <PermissionWrapper requiredPermissions={['Delete']}><Popconfirm title={t('patchManager.baseline.deleteTitle')} description={t('patchManager.baseline.deleteConfirm', undefined, { name: r.name })} onConfirm={async () => { await api.deleteBaseline(r.id); message.success(t('patchManager.baseline.deleted')); await loadData(); }} okText={t('patchManager.delete')} cancelText={t('patchManager.cancel')}>
              <Button type="link" size="small" danger>{t('patchManager.delete')}</Button>
            </Popconfirm></PermissionWrapper>;
        const assessEl = (
          <PermissionWrapper requiredPermissions={['Add']} permissionPath="/patch-manager/risk-execution">
            <Popconfirm
              title={t('patchManager.baseline.assessTitle')}
              description={t('patchManager.baseline.assessConfirm', undefined, { name: r.name, count: r.bound_host_count || 0 })}
              okText={t('patchManager.baseline.confirmAssess')}
              cancelText={t('patchManager.cancel')}
              disabled={!r.can_assess}
              onConfirm={async () => {
                const result = await api.assessBaseline(r.id);
                message.success(t('patchManager.baseline.assessCreated', undefined, { count: result.host_count || 0 }));
                await loadData();
              }}
            >
              <Button type="link" size="small" disabled={!r.can_assess}>
                {t('patchManager.dashboard.assessNow')}
              </Button>
            </Popconfirm>
          </PermissionWrapper>
        );
        return (
          <Space size={12}>
            {r.can_assess ? assessEl : <Tooltip title={r.assess_disabled_reason || t('patchManager.baseline.cannotAssess')}><span>{assessEl}</span></Tooltip>}
            {editEl}
            {bindEl}
            {deleteBlocked ? <Tooltip title={deleteTip}><span>{deleteEl}</span></Tooltip> : deleteEl}
          </Space>
        );
      },
    },
  ];

  const reqColumns = [
    { title: t('patchManager.baseline.requirement'), width: 120, render: (_: unknown, r: any) => r.patch_kb_number || r.patch_pkg_name || '' },
    { title: t('patchManager.severity'), dataIndex: 'patch_severity', width: 90, render: (v: string) => <SeverityTag severity={v} /> },
    { title: t('patchManager.baseline.description'), dataIndex: 'patch_title', ellipsis: true },
    { title: t('patchManager.baseline.applicableVersion'), dataIndex: 'patch_version', width: 100, render: (v: string) => v || '--' },
    { title: t('patchManager.arch'), dataIndex: 'patch_arch', width: 80, render: (v: string) => formatArchitectures(v, '--') },
    {
      title: t('patchManager.operation'),
      width: 60,
      fixed: 'right' as const,
      render: (_: unknown, r: any) => (
        <Button
          type="link"
          size="small"
          danger
          onClick={() => {
            setRequirements((prev) => prev.filter((item) => item.patch !== r.patch));
          }}
        >
          {t('patchManager.baseline.remove')}
        </Button>
      ),
    },
  ];

  const selectedHostRecords = useMemo(() => {
    const recordMap = new Map<number, any>();
    hostCacheRef.current.forEach((h, id) => recordMap.set(id, h));
    return selectedHosts
      .map((key) => recordMap.get(Number(key)))
      .filter(Boolean);
  }, [selectedHosts, bindHostList]);
  const bindPermissionBlocked = selectedHostRecords.some(
    (record) => !record.permission?.includes('Operate'),
  );

  const selectedPatchRecords = useMemo(() => {
    const recordMap = new Map<number, any>();
    patchCacheRef.current.forEach((p, id) => recordMap.set(id, p));
    requirements.forEach((r) => {
      if (!recordMap.has(r.patch)) {
        recordMap.set(r.patch, {
          id: r.patch,
          title: r.patch_title,
          severity: r.patch_severity,
          windows_detail:
            draftOs === 'win'
              ? {
                kb_number: r.patch_kb_number,
                product_list: r.patch_version ? r.patch_version.split('、') : [],
                architectures: normalizeArchitectures(r.patch_arch),
              }
              : null,
          linux_detail:
            draftOs === 'linux'
              ? {
                pkg_name: r.patch_pkg_name,
                os_version_range: r.patch_version,
                distro_name: r.patch_version,
                architectures: normalizeArchitectures(r.patch_arch),
              }
              : null,
        });
      }
    });
    return pickerSelected
      .map((key) => recordMap.get(Number(key)))
      .filter(Boolean);
  }, [pickerSelected, patchList, requirements, draftOs]);
  return (
    <div style={{ background: 'var(--color-bg-1, #fff)', border: '1px solid var(--color-border-1, #e8e8e8)', borderRadius: 10, padding: '16px', flex: 1, minHeight: 0, display: 'flex', flexDirection: 'column' }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', flexWrap: 'wrap', gap: 10, marginBottom: 14 }}>
        <Input.Search
          placeholder={t('patchManager.baseline.name')}
          value={baselineSearch}
          onChange={(e) => setBaselineSearch(e.target.value)}
          onSearch={(v) => { setPagination((p) => ({ ...p, current: 1 })); loadData(1, pagination.pageSize, v); }}
          style={{ width: 220 }}
        />
        <Space size={0}>
          <PermissionWrapper requiredPermissions={['Add']}><Button type="primary" icon={<PlusOutlined />} onClick={() => { setEditing(null); setDraftOs('win'); setRequirements([]); setOriginalRequirements([]); form.resetFields(); setEditOpen(true); }}>{t('patchManager.baseline.create')}</Button></PermissionWrapper>
          <TimeSelector
            onlyRefresh
            customFrequencyList={pollFrequencyOptions}
            onFrequenceChange={setPollIntervalMs}
            onRefresh={() => loadData()}
          />
        </Space>
      </div>
      <div style={{ flex: 1, minHeight: 0 }}>
        <CustomTable
          columns={columns as any}
          dataSource={data}
          rowKey="id"
          loading={listLoading}
          pagination={{
            current: pagination.current,
            pageSize: pagination.pageSize,
            total: pagination.total,
            showSizeChanger: true,
            showTotal: (total) => t('patchManager.common.totalItems', undefined, { count: total }),
            style: { marginBottom: 0 },
            onChange: (page, pageSize) => loadData(page, pageSize),
          }}
        />
      </div>

      <OperateDrawer
        title={editing ? t('patchManager.baseline.edit') : t('patchManager.baseline.create')}
        open={editOpen}
        onClose={() => setEditOpen(false)}
        width={880}
        footer={
          <Space>
            <Button onClick={() => setEditOpen(false)}>{t('patchManager.cancel')}</Button>
            <Tooltip title={requirements.length === 0 ? t('patchManager.baseline.requirementRequired') : ''}>
              <span>
                <PermissionWrapper requiredPermissions={[editing ? 'Edit' : 'Add']}>
                  <Button
                    type="primary"
                    disabled={requirements.length === 0 || reqLoading}
                    loading={saving}
                    onClick={async () => {
                      const values = await form.validateFields();
                      const payload = { name: values.name, os_type: draftOs === 'win' ? 'windows' : 'linux', description: values.description || '' };
                      const currentPatchIds = requirements.map((r) => r.patch);
                      const originalPatchIds = new Set(originalRequirements.map((r) => r.patch));
                      const toAdd = currentPatchIds.filter((id) => !originalPatchIds.has(id));
                      const toRemoveIds = originalRequirements.filter((r) => !currentPatchIds.includes(r.patch)).map((r) => r.id);
                      const latestEditing = data.find((item) => item.id === editing?.id) || editing;
                      if (
                        latestEditing?.is_assessing
                      && (toAdd.length > 0 || toRemoveIds.length > 0)
                      && !(await confirmInvalidateAssessment(editing.name))
                      ) return;
                      setSaving(true);
                      try {
                        let baseline = editing;
                        if (editing) {
                          await api.updateBaseline(editing.id, payload);
                        } else {
                          baseline = await api.createBaseline(payload);
                          setEditing(baseline);
                        }
                        const baselineId = baseline?.id || editing?.id;
                        if (toAdd.length) await api.addBaselineRequirements(baselineId, { patch_ids: toAdd });
                        if (toRemoveIds.length) await api.removeBaselineRequirements(baselineId, toRemoveIds);
                        setOriginalRequirements(requirements);
                        message.success(t('patchManager.baseline.saved'));
                        setEditOpen(false);
                        await loadData();
                      } catch { } finally { setSaving(false); }
                    }}
                  >
                    {t('patchManager.save')}
                  </Button>
                </PermissionWrapper>
              </span>
            </Tooltip>
          </Space>
        }
      >
        <Spin spinning={reqLoading}>
        <Form layout="vertical" form={form} style={{ marginTop: 4 }}>
          <Space style={{ display: 'flex' }} align="start">
            <Form.Item label={t('patchManager.baseline.name')} name="name" rules={[{ required: true, message: t('patchManager.baseline.nameRequired') }]} style={{ flex: 1 }}><Input style={{ width: 300 }} /></Form.Item>
            <Form.Item label={t('patchManager.osType')} required>
              <Select value={draftOs} style={{ width: 130 }} disabled={!!editing} onChange={setDraftOs} options={[{ label: 'Windows', value: 'win' }, { label: 'Linux', value: 'linux' }]} />
            </Form.Item>
          </Space>
          {editing && <Alert style={{ marginBottom: 12 }} type="info" showIcon message={t('patchManager.baseline.osLocked')} />}
          <Form.Item label={t('patchManager.baseline.description')} name="description"><Input.TextArea rows={2} placeholder={t('patchManager.baseline.descriptionPlaceholder')} /></Form.Item>
          <div style={{ display: 'flex', alignItems: 'center', gap: 8, margin: '4px 0 8px' }}>
            <span style={{ fontWeight: 500 }}>{t('patchManager.baseline.requirementList')}</span>
            <Tag color="warning">{t('patchManager.baseline.allRequired')}</Tag>
          </div>
          <Table size="small" pagination={false} dataSource={requirements} rowKey={(r: any) => r.id ?? r.patch} columns={reqColumns as any} scroll={{ x: 780 }} />
          <div style={{ marginTop: 8 }}>
            {draftOs ? (
              <Button type="link" size="small" icon={<PlusOutlined />} onClick={() => { setPatchPickerOpen(true); }}>{t('patchManager.baseline.addFromLibrary')}</Button>
            ) : (
              <span style={{ color: 'var(--color-text-4, #bfbfbf)', cursor: 'not-allowed' }}><PlusOutlined /> {t('patchManager.baseline.addFromLibrary')}</span>
            )}
          </div>
        </Form>
        </Spin>
      </OperateDrawer>

      <OperateDrawer
        title={t('patchManager.baseline.bindTitle', undefined, { name: bindTarget?.name || '' })}
        open={bindOpen}
        onClose={closeBindDrawer}
        width={880}
        footer={
          <Space>
            <Button onClick={closeBindDrawer}>{t('patchManager.cancel')}</Button>
            <Tooltip title={selectedHosts.length === 0 ? t('patchManager.baseline.targetRequired') : ''}>
              <PermissionWrapper requiredPermissions={['Edit']} permissionPath="/patch-manager/target">
                <Button
                  type="primary"
                    disabled={selectedHosts.length === 0 || bindDrawerLoading || bindPermissionBlocked}
                  loading={bindSaving}
                  onClick={async () => {
                    if (!bindTarget || selectedHosts.length === 0) return;
                    const hostIds = selectedHosts.map((k) => Number(k)).filter((id) => !isNaN(id));
                    const originalHostIds = originalSelectedHosts
                      .map((k) => Number(k))
                      .filter((id) => !isNaN(id));
                    const bindingChanged = hostIds.length !== originalHostIds.length
                    || hostIds.some((id) => !originalHostIds.includes(id));
                    const latestBaseline = data.find((item) => item.id === bindTarget.id) || bindTarget;
                    setBindSaving(true);
                    try {
                      if (
                        latestBaseline.is_assessing
                      && bindingChanged
                      && !(await confirmInvalidateAssessment(bindTarget.name))
                      ) return;
                      await api.bindHostsToBaseline(bindTarget.id, hostIds);
                      message.success(t('patchManager.baseline.targetsBound', undefined, { count: hostIds.length }));
                      closeBindDrawer();
                      await loadData();
                    } catch {
                    } finally {
                      setBindSaving(false);
                    }
                  }}
                >
                  {t('patchManager.baseline.confirmBind')}
                </Button>
              </PermissionWrapper>
            </Tooltip>
          </Space>
        }
      >
        <DualSelector
          rowKey="id"
          dataSource={bindHostList}
          loading={bindDrawerLoading}
          pagination={{
            current: bindHostPagination.current,
            pageSize: bindHostPagination.pageSize,
            total: bindHostPagination.total,
            showSizeChanger: true,
            showTotal: (total) => t('patchManager.common.totalItems', undefined, { count: total }),
          }}
          onPageChange={(page, pageSize) => loadBindHosts(page, pageSize)}
          columns={[
            { title: t('patchManager.baseline.target'), dataIndex: 'name', width: 110 },
            { title: 'IP', dataIndex: 'ip', width: 130 },
            { title: t('patchManager.osType'), dataIndex: 'os_type_display', width: 90 },
          ]}
          selectedKeys={selectedHosts}
          onChange={setSelectedHosts}
          selectedRecordsData={selectedHostRecords}
          renderSelectedLabel={(r) => r.name}
          leftTitle={<Input.Search placeholder={t('patchManager.baseline.targetSearch')} value={hostSearch} onSearch={(v) => { setBindHostPagination((p) => ({ ...p, current: 1 })); loadBindHosts(1, bindHostPagination.pageSize, v); }} onChange={(e) => setHostSearch(e.target.value)} allowClear style={{ width: 240, marginBottom: 12 }} />}
          rightTitle={t('patchManager.baseline.selectedTargets', undefined, { count: selectedHosts.length })}
          height="calc(100vh - 200px)"
        />
      </OperateDrawer>

      <OperateDrawer
        title={t('patchManager.baseline.addFromLibrary')}
        open={patchPickerOpen}
        onClose={closePatchPicker}
        width={960}
        footer={
          <Space>
            <Button onClick={closePatchPicker}>{t('patchManager.cancel')}</Button>
            <Tooltip title={pickerSelected.length === 0 ? t('patchManager.baseline.patchRequired') : ''}>
              <span>
                <Button
                  type="primary"
                  disabled={pickerSelected.length === 0}
                  onClick={() => {
                    const recordMap = new Map<number, any>();
                    patchCacheRef.current.forEach((p, id) => recordMap.set(id, p));
                    requirements.forEach((r) => {
                      if (!recordMap.has(r.patch)) {
                        recordMap.set(r.patch, r);
                      }
                    });
                    const nextRequirements = pickerSelected
                      .map((key) => {
                        const patch = recordMap.get(Number(key));
                        if (!patch) return null;
                        if (patch.title === undefined) {
                          return patch;
                        }
                        return {
                          patch: patch.id,
                          patch_title: patch.title,
                          patch_severity: patch.severity,
                          patch_kb_number: patch.windows_detail?.kb_number,
                          patch_pkg_name: patch.linux_detail?.pkg_name,
                          patch_pkg_version: patch.linux_detail?.pkg_version,
                          patch_version:
                            patch.windows_detail?.product_list?.join('、')
                            || patch.linux_detail?.os_version_range
                            || patch.linux_detail?.distro_name
                            || '',
                          patch_arch:
                            patch.windows_detail?.architectures?.join('、')
                            || patch.linux_detail?.architectures?.join('、')
                            || '',
                        };
                      })
                      .filter(Boolean);
                    setRequirements(nextRequirements);
                    closePatchPicker();
                  }}
                >
                  {t('patchManager.baseline.confirmAdd')}
                </Button>
              </span>
            </Tooltip>
          </Space>
        }
      >
        <Alert style={{ marginBottom: 12 }} type="info" showIcon message={t('patchManager.baseline.libraryHelp')} />
        <DualSelector
          rowKey="id"
          dataSource={patchList}
          loading={patchPickerLoading}
          pagination={{
            current: patchPickerPagination.current,
            pageSize: patchPickerPagination.pageSize,
            total: patchPickerPagination.total,
            showSizeChanger: true,
            showTotal: (total) => t('patchManager.common.totalItems', undefined, { count: total }),
          }}
          onPageChange={(page, pageSize) => loadPatches(page, pageSize)}
          columns={[
            { title: draftOs === 'win' ? t('patchManager.kbNumber') : t('patchManager.packageName'), width: 120, render: (_: unknown, r: any) => r.windows_detail?.kb_number || r.linux_detail?.pkg_name || '' },
            { title: t('patchManager.severity'), dataIndex: 'severity', width: 90, render: (v: string) => <SeverityTag severity={v} /> },
            { title: t('patchManager.baseline.description'), dataIndex: 'title', ellipsis: true },
            { title: t('patchManager.baseline.applicableVersion'), width: 100, render: (_: unknown, r: any) => r.windows_detail?.product_list?.join('、') || r.linux_detail?.os_version_range || r.linux_detail?.distro_name || '--' },
            { title: t('patchManager.arch'), width: 80, render: (_: unknown, r: any) => formatArchitectures(r.windows_detail?.architectures || r.linux_detail?.architectures, '--') },
          ]}
          selectedKeys={pickerSelected}
          onChange={setPickerSelected}
          getCheckboxProps={(record) => ({ disabled: !record.permission?.includes('Operate') })}
          selectedRecordsData={selectedPatchRecords}
          renderSelectedLabel={(r) => r.windows_detail?.kb_number || r.linux_detail?.pkg_name || r.title}
          leftTitle={
            <Input.Search
              placeholder={draftOs === 'win' ? t('patchManager.baseline.searchKb') : t('patchManager.baseline.searchPackage')}
              value={patchSearch}
              onSearch={(v) => { setPatchPickerPagination((p) => ({ ...p, current: 1 })); loadPatches(1, patchPickerPagination.pageSize, v); }}
              onChange={(e) => setPatchSearch(e.target.value)}
              allowClear
              style={{ width: 300, marginBottom: 12 }}
            />
          }
          height="calc(100vh - 240px)"
        />
      </OperateDrawer>
    </div>
  );
}
