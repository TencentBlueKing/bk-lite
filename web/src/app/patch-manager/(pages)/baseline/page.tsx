'use client';

import React, { useState, useRef, useEffect, useMemo } from 'react';
import { Table, Tag, Button, Input, Space, Form, Select, Alert, Tooltip, message, Popconfirm, Spin, Modal } from 'antd';
import PermissionWrapper from '@/components/permission';
import { PlusOutlined } from '@ant-design/icons';
import useApiClient from '@/utils/request';
import usePatchManagerApi from '@/app/patch-manager/api';
import DualSelector from '@/app/patch-manager/components/dual-selector';
import SeverityTag from '@/app/patch-manager/components/severity-tag';
import CustomTable from '@/components/custom-table';
import OperateDrawer from '@/app/patch-manager/components/operate-drawer';
import { useRouter } from 'next/navigation';
import { useLocalizedTime } from '@/hooks/useLocalizedTime';

export default function BaselineManagementPage() {
  const router = useRouter();
  const { convertToLocalizedTime } = useLocalizedTime();
  const api = usePatchManagerApi();
  const { isLoading } = useApiClient();
  const [data, setData] = useState<any[]>([]);
  const [loading, setLoading] = useState(false);
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
  const [pagination, setPagination] = useState({ current: 1, pageSize: 20, total: 0 });
  const baselineAbortRef = useRef<AbortController | null>(null);
  const baselineRequestSeq = useRef(0);

  const confirmInvalidateAssessment = (baselineName: string) => new Promise<boolean>((resolve) => {
    Modal.confirm({
      title: '当前评估将失效',
      content: `“${baselineName}”正在评估中。修改补丁要求或绑定主机后，未开始的评估会取消，运行中的结果不会回写。是否继续？`,
      okText: '继续修改',
      cancelText: '取消',
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
    baselineAbortRef.current?.abort();
    const controller = new AbortController();
    baselineAbortRef.current = controller;
    const seq = ++baselineRequestSeq.current;
    if (!silent) setLoading(true);
    try {
      const res = await api.getBaselineList(
        { page, page_size: pageSize, search: search || undefined },
        { signal: controller.signal },
      );
      if (seq !== baselineRequestSeq.current) return;
      setData(res.items || []);
      setPagination((p) => ({ ...p, current: page, pageSize, total: res.count || 0 }));
    } catch {
      if (controller.signal.aborted) return;
      setData([]);
      setPagination((p) => ({ ...p, current: page, pageSize, total: 0 }));
    } finally {
      if (!silent && seq === baselineRequestSeq.current) setLoading(false);
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
    if (isLoading) return;
    const timer = window.setInterval(() => {
      if (!document.hidden) baselinePollRef.current();
    }, 2000);
    return () => {
      window.clearInterval(timer);
      baselineAbortRef.current?.abort();
      baselineRequestSeq.current += 1;
    };
  }, [isLoading]);

  useEffect(() => {
    if (!editOpen) return;
    if (!editing) {
      setRequirements([]);
      setOriginalRequirements([]);
      return;
    }
    let cancelled = false;
    setReqLoading(true);
    loadRequirements(editing.id).then((reqs) => {
      if (cancelled) return;
      setOriginalRequirements(reqs);
      setReqLoading(false);
    });
    return () => { cancelled = true; };
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

  const loadRequirements = async (baselineId: number) => {
    try {
      const reqs = await api.getBaselineRequirements(baselineId);
      setRequirements(reqs || []);
      return reqs || [];
    } catch {
      setRequirements([]);
      return [];
    }
  };

  const patchesAbortRef = useRef<AbortController | null>(null);
  const loadPatches = async (
    page = patchPickerPagination.current,
    pageSize = patchPickerPagination.pageSize,
    name = patchSearch,
  ) => {
    setPatchPickerLoading(true);
    patchesAbortRef.current?.abort();
    const controller = new AbortController();
    patchesAbortRef.current = controller;
    try {
      const res = await api.getPatchList(
        {
          page,
          page_size: pageSize,
          os_type: draftOs === 'win' ? 'windows' : 'linux',
          pkg_status: 'ready',
          name: name || undefined,
        },
        { signal: controller.signal },
      );
      setPatchList(res.items || []);
      (res.items || []).forEach((p: any) => patchCacheRef.current.set(p.id, p));
      setPatchPickerPagination((p) => ({ ...p, current: page, pageSize, total: res.count || 0 }));
    } catch {
      setPatchList([]);
      setPatchPickerPagination((p) => ({ ...p, current: page, pageSize, total: 0 }));
    } finally {
      setPatchPickerLoading(false);
      patchesAbortRef.current = null;
    }
  };

  const loadBindHosts = async (page = 1, pageSize = 20, search = hostSearch) => {
    if (!bindTarget) return;
    setBindDrawerLoading(true);
    try {
      const res = await api.getPatchTargetList({
        page,
        page_size: pageSize,
        os_type: bindTarget.os_type,
        search: search || undefined,
      });
      setBindHostList(res.items || []);
      setBindHostPagination({ current: page, pageSize, total: res.count || 0 });
      (res.items || []).forEach((h: any) => hostCacheRef.current.set(h.id, h));
    } catch {
      setBindHostList([]);
      setBindHostPagination({ current: page, pageSize, total: 0 });
    } finally {
      setBindDrawerLoading(false);
    }
  };

  const columns = [
    { title: '基线名称', dataIndex: 'name', width: 170 },
    { title: '操作系统', dataIndex: 'os_type_display', width: 100 },
    { title: '绑定主机', dataIndex: 'bound_host_count', width: 90, render: (v: number) => `${v || 0} 台` },
    {
      title: '合规分布',
      dataIndex: 'compliance_distribution',
      width: 280,
      render: (dist: any[], r: any) => {
        const items = dist || [];
        if (!items.length) {
          return r.bound_host_count ? '—' : <span style={{ color: 'var(--color-text-4, #bfbfbf)' }}>未绑定</span>;
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
                {item.label} {item.count}
              </Tag>
            ))}
          </Space>
        );
      },
    },
    { title: '更新时间', dataIndex: 'updated_at', width: 180, render: (v: string | null) => convertToLocalizedTime(v) || '—' },
    {
      title: '操作',
      dataIndex: 'op',
      width: 250,
      render: (_: unknown, r: any) => {
        const deleteBlocked = (r.bound_host_count || 0) > 0;
        const deleteTip = deleteBlocked ? '该基线已绑定主机，不能删除' : '';
        const editEl = <PermissionWrapper requiredPermissions={['Edit']}><Button type="link" size="small" onClick={() => { setEditing(r); setDraftOs(r.os_type === 'windows' ? 'win' : 'linux'); form.setFieldsValue({ name: r.name, description: r.description }); setEditOpen(true); }}>编辑</Button></PermissionWrapper>;
        const bindEl = <PermissionWrapper requiredPermissions={['Edit']}><Button type="link" size="small" onClick={async () => {
          setBindTarget(r);
          setSelectedHosts([]);
          setOriginalSelectedHosts([]);
          setHostSearch('');
          setBindDrawerLoading(true);
          setBindOpen(true);
          hostCacheRef.current = new Map();
          setBindHostPagination({ current: 1, pageSize: 20, total: 0 });
          try {
            const [hostsRes, bindings] = await Promise.all([
              api.getPatchTargetList({ page: 1, page_size: 20, os_type: r.os_type }),
              api.getBaselineHosts(r.id),
            ]);
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
                });
              }
            });
            const bindingTargetIds = (bindings || []).map((i: any) => i.target);
            setSelectedHosts(bindingTargetIds);
            setOriginalSelectedHosts(bindingTargetIds);
          } catch {
            setBindHostList([]);
          } finally {
            setBindDrawerLoading(false);
          }
        }}>绑定主机</Button></PermissionWrapper>;
        const deleteEl = deleteBlocked
          ? <Button type="link" size="small" danger disabled>删除</Button>
          : <PermissionWrapper requiredPermissions={['Delete']}><Popconfirm title="删除基线" description={`确定删除 ${r.name} 吗？`} onConfirm={async () => { await api.deleteBaseline(r.id); message.success('已删除'); loadData(); }} okText="删除" cancelText="取消">
              <Button type="link" size="small" danger>删除</Button>
            </Popconfirm></PermissionWrapper>;
        const assessEl = (
          <PermissionWrapper requiredPermissions={['Edit']}>
            <Button
              type="link"
              size="small"
              disabled={!r.can_assess}
              onClick={() => {
                if (!r.can_assess) return;
                Modal.confirm({
                  title: '立即评估基线',
                  content: `将评估“${r.name}”当前绑定的 ${r.bound_host_count || 0} 台主机，是否继续？`,
                  okText: '确认评估',
                  cancelText: '取消',
                  async onOk() {
                    const result = await api.assessBaseline(r.id);
                    message.success(`评估任务已创建，共 ${result.host_count || 0} 台主机`);
                    await loadData();
                  },
                });
              }}
            >
              立即评估
            </Button>
          </PermissionWrapper>
        );
        return (
          <Space size={12}>
            {r.can_assess ? assessEl : <Tooltip title={r.assess_disabled_reason || '当前不可评估'}><span>{assessEl}</span></Tooltip>}
            {editEl}
            {bindEl}
            {deleteBlocked ? <Tooltip title={deleteTip}><span>{deleteEl}</span></Tooltip> : deleteEl}
          </Space>
        );
      },
    },
  ];

  const reqColumns = [
    { title: '要求', width: 120, render: (_: unknown, r: any) => r.patch_kb_number || r.patch_pkg_name || '' },
    { title: '严重级别', dataIndex: 'patch_severity', width: 90, render: (v: string) => <SeverityTag severity={v} /> },
    { title: '描述', dataIndex: 'patch_title', ellipsis: true },
    { title: '适用版本', dataIndex: 'patch_version', width: 100 },
    { title: '架构', dataIndex: 'patch_arch', width: 80 },
    {
      title: '操作',
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
          移除
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
                architectures: r.patch_arch ? r.patch_arch.split('、') : [],
              }
              : null,
          linux_detail:
            draftOs === 'linux'
              ? {
                pkg_name: r.patch_pkg_name,
                os_version_range: r.patch_version,
                distro_name: r.patch_version,
                architectures: r.patch_arch ? r.patch_arch.split('、') : [],
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
          placeholder="基线名称"
          value={baselineSearch}
          onChange={(e) => setBaselineSearch(e.target.value)}
          onSearch={(v) => { setPagination((p) => ({ ...p, current: 1 })); loadData(1, pagination.pageSize, v); }}
          style={{ width: 220 }}
        />
        <PermissionWrapper requiredPermissions={['Add']}><Button type="primary" icon={<PlusOutlined />} onClick={() => { setEditing(null); setDraftOs('win'); setRequirements([]); setOriginalRequirements([]); form.resetFields(); setEditOpen(true); }}>新建基线</Button></PermissionWrapper>
      </div>
      <div style={{ flex: 1, minHeight: 0 }}>
        <CustomTable
          columns={columns as any}
          dataSource={data}
          rowKey="id"
          loading={loading}
          pagination={{
            current: pagination.current,
            pageSize: pagination.pageSize,
            total: pagination.total,
            showSizeChanger: true,
            showTotal: (t) => `共 ${t} 条`,
            style: { marginBottom: 0 },
            onChange: (page, pageSize) => loadData(page, pageSize),
          }}
        />
      </div>

      <OperateDrawer
        title={editing ? '编辑基线' : '新建基线'}
        open={editOpen}
        onClose={() => setEditOpen(false)}
        width={880}
        footer={
          <Space>
            <Button onClick={() => setEditOpen(false)}>取消</Button>
            <Tooltip title={requirements.length === 0 ? '请至少添加一条补丁要求' : ''}>
              <span>
                <Button
                  type="primary"
                  disabled={requirements.length === 0 || reqLoading}
                  loading={loading}
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
                    setLoading(true);
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
                      message.success('保存成功');
                      setEditOpen(false); loadData();
                    } catch { } finally { setLoading(false); }
                  }}
                >
                  保存
                </Button>
              </span>
            </Tooltip>
          </Space>
        }
      >
        <Spin spinning={reqLoading}>
        <Form layout="vertical" form={form} style={{ marginTop: 4 }}>
          <Space style={{ display: 'flex' }} align="start">
            <Form.Item label="基线名称" name="name" rules={[{ required: true, message: '请输入基线名称' }]} style={{ flex: 1 }}><Input style={{ width: 300 }} /></Form.Item>
            <Form.Item label="操作系统" required>
              <Select value={draftOs} style={{ width: 130 }} disabled={!!editing} onChange={setDraftOs} options={[{ label: 'Windows', value: 'win' }, { label: 'Linux', value: 'linux' }]} />
            </Form.Item>
          </Space>
          {editing && <Alert style={{ marginBottom: 12 }} type="info" showIcon message="操作系统创建后锁定，编辑时不可修改。确需其他操作系统请新建基线。" />}
          <Form.Item label="说明" name="description"><Input.TextArea rows={2} placeholder="基线说明" /></Form.Item>
          <div style={{ display: 'flex', alignItems: 'center', gap: 8, margin: '4px 0 8px' }}>
            <span style={{ fontWeight: 500 }}>补丁要求清单</span>
            <Tag color="warning">全部必装</Tag>
          </div>
          <Table size="small" pagination={false} dataSource={requirements} rowKey={(r: any) => r.id ?? r.patch} columns={reqColumns as any} scroll={{ x: 780 }} />
          <div style={{ marginTop: 8 }}>
            {draftOs ? (
              <Button type="link" size="small" icon={<PlusOutlined />} onClick={() => { setPatchPickerOpen(true); }}>从补丁库添加要求</Button>
            ) : (
              <span style={{ color: 'var(--color-text-4, #bfbfbf)', cursor: 'not-allowed' }}><PlusOutlined /> 从补丁库添加要求</span>
            )}
          </div>
        </Form>
        </Spin>
      </OperateDrawer>

      <OperateDrawer
        title={`绑定主机 - ${bindTarget?.name || ''}`}
        open={bindOpen}
        onClose={() => setBindOpen(false)}
        width={880}
        footer={
          <Space>
            <Button onClick={() => setBindOpen(false)}>取消</Button>
            <Tooltip title={selectedHosts.length === 0 ? '请至少选择一台主机' : ''}>
              <Button
                type="primary"
                disabled={selectedHosts.length === 0 || bindDrawerLoading}
                onClick={async () => {
                  if (!bindTarget || selectedHosts.length === 0) return;
                  const hostIds = selectedHosts.map((k) => Number(k)).filter((id) => !isNaN(id));
                  const originalHostIds = originalSelectedHosts
                    .map((k) => Number(k))
                    .filter((id) => !isNaN(id));
                  const bindingChanged = hostIds.length !== originalHostIds.length
                    || hostIds.some((id) => !originalHostIds.includes(id));
                  const latestBaseline = data.find((item) => item.id === bindTarget.id) || bindTarget;
                  try {
                    if (
                      latestBaseline.is_assessing
                      && bindingChanged
                      && !(await confirmInvalidateAssessment(bindTarget.name))
                    ) return;
                    await api.bindHostsToBaseline(bindTarget.id, hostIds);
                    message.success(`已将 ${hostIds.length} 台主机绑定到当前基线`);
                    setBindOpen(false);
                    loadData();
                  } catch {
                  }
                }}
              >
                确认绑定
              </Button>
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
            showTotal: (t) => `共 ${t} 条`,
          }}
          onPageChange={(page, pageSize) => loadBindHosts(page, pageSize)}
          columns={[
            { title: '主机', dataIndex: 'name', width: 110 },
            { title: 'IP', dataIndex: 'ip', width: 130 },
            { title: '操作系统', dataIndex: 'os_type_display', width: 90 },
          ]}
          selectedKeys={selectedHosts}
          onChange={setSelectedHosts}
          selectedRecordsData={selectedHostRecords}
          renderSelectedLabel={(r) => r.name}
          leftTitle={<Input.Search placeholder="主机名 / IP" value={hostSearch} onSearch={(v) => { setBindHostPagination((p) => ({ ...p, current: 1 })); loadBindHosts(1, bindHostPagination.pageSize, v); }} onChange={(e) => setHostSearch(e.target.value)} allowClear style={{ width: 240, marginBottom: 12 }} />}
          rightTitle={`已选 ${selectedHosts.length} 台`}
          height="calc(100vh - 200px)"
        />
      </OperateDrawer>

      <OperateDrawer
        title="从补丁库添加要求"
        open={patchPickerOpen}
        onClose={() => setPatchPickerOpen(false)}
        width={960}
        footer={
          <Space>
            <Button onClick={() => setPatchPickerOpen(false)}>取消</Button>
            <Tooltip title={pickerSelected.length === 0 ? '请至少选择一条补丁' : ''}>
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
                    setPatchPickerOpen(false);
                  }}
                >
                  确认添加
                </Button>
              </span>
            </Tooltip>
          </Space>
        }
      >
        <Alert style={{ marginBottom: 12 }} type="info" showIcon message="仅展示「就绪」状态的补丁；勾选加入当前基线清单，取消勾选移除。" />
        <DualSelector
          rowKey="id"
          dataSource={patchList}
          loading={patchPickerLoading}
          pagination={{
            current: patchPickerPagination.current,
            pageSize: patchPickerPagination.pageSize,
            total: patchPickerPagination.total,
            showSizeChanger: true,
            showTotal: (t) => `共 ${t} 条`,
          }}
          onPageChange={(page, pageSize) => loadPatches(page, pageSize)}
          columns={[
            { title: draftOs === 'win' ? 'KB 号' : '包名', width: 120, render: (_: unknown, r: any) => r.windows_detail?.kb_number || r.linux_detail?.pkg_name || '' },
            { title: '严重级别', dataIndex: 'severity', width: 90, render: (v: string) => <SeverityTag severity={v} /> },
            { title: '描述', dataIndex: 'title', ellipsis: true },
            { title: '适用版本', width: 100, render: (_: unknown, r: any) => r.windows_detail?.product_list?.join('、') || r.linux_detail?.os_version_range || r.linux_detail?.distro_name || '-' },
            { title: '架构', width: 80, render: (_: unknown, r: any) => r.windows_detail?.architectures?.join('、') || r.linux_detail?.architectures?.join('、') || '-' },
          ]}
          selectedKeys={pickerSelected}
          onChange={setPickerSelected}
          selectedRecordsData={selectedPatchRecords}
          renderSelectedLabel={(r) => r.windows_detail?.kb_number || r.linux_detail?.pkg_name || r.title}
          leftTitle={
            <Input.Search
              placeholder={draftOs === 'win' ? '搜索 KB 号' : '搜索包名'}
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
