'use client';

import React, { useEffect, useState } from 'react';
import { Button, Checkbox, Drawer, Dropdown, Input, Modal, Popconfirm, Select, Spin, Tag, message } from 'antd';
import { PlusOutlined } from '@ant-design/icons';
import SearchActionBar from '@/components/search-action-bar';
import { useSearchParams } from 'next/navigation';
import { cloneDeep } from 'lodash';
import useApiClient from '@/utils/request';
import useMonitorApi from '@/app/monitor/api';
import useIntegrationApi from '@/app/monitor/api/integration';
import useEventApi from '@/app/monitor/api/event';
import { useTranslation } from '@/utils/i18n';
import { ColumnItem, ObjectItem, Pagination, TableDataItem, TreeItem, UserItem } from '@/app/monitor/types';
import { findLabelById } from '@/app/monitor/utils/common';
import CustomTable from '@/components/custom-table';
import TreeSelector from '@/app/monitor/components/treeSelector';
import ResizableSidebar from '@/app/monitor/components/resizableSidebar';
import Permission from '@/components/permission';
import { useCommon } from '@/app/monitor/context/common';
import { useMonitorObjectQuery } from '@/app/monitor/hooks/useMonitorObjectQuery';
import { resolveMonitorObjectQueryId, resolveMonitorObjectTreeKey } from '@/app/monitor/utils/monitorObjectQuery';
import assetStyle from '../strategy/index.module.scss';
import ThresholdList, { ThresholdItem } from '../strategy/detail/thresholdList';

interface PolicyGroupRule {
  id: number;
  name: string;
  plugin_name: string;
  threshold: Array<{ level?: string; method?: string; value?: number }>;
  notice_users: string[];
}

interface PolicyGroupRow {
  id: number;
  name: string;
  is_default?: boolean;
  member_count: number;
  rules: PolicyGroupRule[];
}

interface TemplateOption {
  id: number;
  name: string;
  pluginName: string;
}

const MEMBER_STATE: Record<string, string> = {
  member: '在组',
  declined: '不自动入组',
  skipped: '未入组',
};

interface InstanceCandidate {
  instance_id?: string;
  instance_name?: string;
  id?: string;
  name?: string;
  ip?: string | null;
  summary_facts?: { 'asset.ip'?: string };
}

const logicalInstanceId = (instanceId: string) => {
  const matched = instanceId.match(/^\('(.*)',\)$/);
  return matched?.[1] || instanceId;
};

const candidateIp = (item: InstanceCandidate) => {
  const ip = String(item.ip || '').trim();
  if (ip) return ip;
  const assetIp = item.summary_facts?.['asset.ip'];
  return typeof assetIp === 'string' ? assetIp.trim() : '';
};

const candidateLabel = (item: InstanceCandidate) => {
  const id = String(item.instance_id || item.id || '');
  const name = String(item.instance_name || item.name || '').trim();
  const ip = candidateIp(item);
  const logicalId = logicalInstanceId(id);
  const opaque = !name || name === id || name === logicalId;
  if (opaque) return ip || name || logicalId;
  if (ip && ip !== name) return `${name} · ${ip}`;
  return name;
};

const PolicyGroupPage: React.FC = () => {
  const { t } = useTranslation();
  const { isLoading } = useApiClient();
  const { getMonitorObject, getInstanceList } = useMonitorApi();
  const {
    getPolicyGroups,
    getPolicyGroupMembers,
    joinPolicyGroup,
    leavePolicyGroup,
    updatePolicyGroupRule,
    copyPolicyGroup,
    setDefaultPolicyGroup,
    deletePolicyGroup,
    createPolicyGroup,
  } = useIntegrationApi();
  const { getPolicyTemplate } = useEventApi();
  const searchParams = useSearchParams();
  const { syncObjectId } = useMonitorObjectQuery();
  const users: UserItem[] = useCommon()?.userList || [];
  const [treeLoading, setTreeLoading] = useState(false);
  const [treeData, setTreeData] = useState<TreeItem[]>([]);
  const [selectedKey, setSelectedKey] = useState('');
  const [objectId, setObjectId] = useState<React.Key>('');
  const [groups, setGroups] = useState<PolicyGroupRow[]>([]);
  const [switchGroups, setSwitchGroups] = useState<PolicyGroupRow[]>([]);
  const [loading, setLoading] = useState(false);
  const [pagination, setPagination] = useState<Pagination>({
    current: 1,
    total: 0,
    pageSize: 20,
  });
  const [searchText, setSearchText] = useState('');
  const [appliedSearch, setAppliedSearch] = useState('');
  const [createOpen, setCreateOpen] = useState(false);
  const [createName, setCreateName] = useState('');
  const [createSaving, setCreateSaving] = useState(false);
  const [templateLoading, setTemplateLoading] = useState(false);
  const [templateOptions, setTemplateOptions] = useState<TemplateOption[]>([]);
  const [selectedTemplateIds, setSelectedTemplateIds] = useState<number[]>([]);
  const [memberGroup, setMemberGroup] = useState<PolicyGroupRow | null>(null);
  const [members, setMembers] = useState<TableDataItem[]>([]);
  const [memberLoading, setMemberLoading] = useState(false);
  const [memberKeyword, setMemberKeyword] = useState('');
  const [joinOpen, setJoinOpen] = useState(false);
  const [joinKeyword, setJoinKeyword] = useState('');
  const [joinRows, setJoinRows] = useState<InstanceCandidate[]>([]);
  const [joinLoading, setJoinLoading] = useState(false);
  const [joinSelected, setJoinSelected] = useState<string[]>([]);
  const [joinLabels, setJoinLabels] = useState<Record<string, string>>({});
  const [joinPagination, setJoinPagination] = useState<Pagination>({
    current: 1,
    total: 0,
    pageSize: 10,
  });
  const [ruleGroup, setRuleGroup] = useState<PolicyGroupRow | null>(null);
  const [rule, setRule] = useState<PolicyGroupRule | null>(null);
  const [thresholdDraft, setThresholdDraft] = useState<ThresholdItem[]>([]);
  const [noticeUsers, setNoticeUsers] = useState<string[]>([]);
  const [copySource, setCopySource] = useState<PolicyGroupRow | null>(null);
  const [copyName, setCopyName] = useState('');

  const loadGroups = async (
    id: React.Key,
    options?: { page?: number; pageSize?: number; name?: string }
  ) => {
    const page = options?.page ?? pagination.current;
    const pageSize = options?.pageSize ?? pagination.pageSize;
    const name = options?.name ?? appliedSearch;
    setLoading(true);
    try {
      const data = await getPolicyGroups({
        monitor_object_id: id,
        name: name || undefined,
        page,
        page_size: pageSize,
      });
      const items = Array.isArray(data) ? data : data?.items || [];
      const total = Array.isArray(data) ? items.length : Number(data?.count || 0);
      if (page > 1 && items.length === 0 && total > 0) {
        setPagination((prev) => ({ ...prev, current: page - 1, total }));
        return;
      }
      setGroups(items);
      setPagination((prev) => ({ ...prev, current: page, pageSize, total }));
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    if (isLoading) return;
    setTreeLoading(true);
    getMonitorObject({ add_instance_count: true })
      .then((data: ObjectItem[]) => {
        const grouped = data.reduce((acc, item) => {
          if (!acc[item.type]) {
            acc[item.type] = { title: item.display_type || '--', key: item.type, children: [] };
          }
          acc[item.type].children.push({
            title: item.display_name || item.name || '--',
            label: item.name || '--',
            key: item.id,
            icon: item.icon,
            children: [],
          });
          return acc;
        }, {} as Record<string, TreeItem>);
        const tree = Object.values(grouped);
        const key = resolveMonitorObjectTreeKey(
          data,
          resolveMonitorObjectQueryId({ searchParams, objects: data, fallback: data[0]?.id }),
          data[0]?.id
        );
        setTreeData(tree);
        setSelectedKey(String(key || ''));
      })
      .finally(() => setTreeLoading(false));
  }, [isLoading]);

  useEffect(() => {
    if (!objectId) return;
    void loadGroups(objectId);
  }, [objectId, pagination.current, pagination.pageSize, appliedSearch]);

  const openMembers = async (group: PolicyGroupRow) => {
    setMemberGroup(group);
    setMemberKeyword('');
    setMemberLoading(true);
    try {
      const [memberRows, allGroups] = await Promise.all([
        getPolicyGroupMembers(group.id),
        getPolicyGroups({ monitor_object_id: objectId, create_default: false }),
      ]);
      setMembers(Array.isArray(memberRows) ? memberRows : []);
      setSwitchGroups(Array.isArray(allGroups) ? allGroups : []);
    } finally {
      setMemberLoading(false);
    }
  };

  const loadJoinInstances = async (page = 1, name = '', pageSize = joinPagination.pageSize) => {
    if (!objectId) return;
    setJoinLoading(true);
    try {
      const data = await getInstanceList(objectId, {
        page,
        page_size: pageSize,
        name: name.trim(),
      });
      const results = (data?.results || []) as InstanceCandidate[];
      setJoinRows(results);
      setJoinLabels((prev) => {
        const next = { ...prev };
        results.forEach((item) => {
          const id = String(item.instance_id || item.id || '');
          if (id) next[id] = candidateLabel(item);
        });
        return next;
      });
      setJoinPagination({ current: page, pageSize, total: Number(data?.count || 0) });
    } finally {
      setJoinLoading(false);
    }
  };

  const openJoin = () => {
    setJoinOpen(true);
    setJoinSelected([]);
    setJoinKeyword('');
    setJoinLabels({});
    void loadJoinInstances(1, '', 10);
  };

  const confirmJoin = async () => {
    if (!memberGroup || joinSelected.length === 0) return;
    await joinPolicyGroup(memberGroup.id, joinSelected);
    message.success('已加入。已在其他组的实例会先离开原组');
    setJoinOpen(false);
    setJoinSelected([]);
    await openMembers(memberGroup);
    await loadGroups(objectId);
  };

  const reloadFirstPage = async () => {
    setSearchText('');
    const unchanged = pagination.current === 1 && appliedSearch === '';
    if (appliedSearch) setAppliedSearch('');
    if (pagination.current !== 1) {
      setPagination((prev) => ({ ...prev, current: 1 }));
    }
    if (unchanged && objectId) await loadGroups(objectId, { page: 1, name: '' });
  };

  const openCreate = async () => {
    setCreateOpen(true);
    setCreateName('新建策略组');
    setSelectedTemplateIds([]);
    setTemplateLoading(true);
    try {
      const monitorName = findLabelById(treeData, String(objectId));
      const data = monitorName ? await getPolicyTemplate({ monitor_object_name: monitorName }) : [];
      const options = (Array.isArray(data) ? data : [])
        .map((item: { id?: number; name?: string; plugin_display_name?: string; plugin_name?: string }) => ({
          id: Number(item.id),
          name: item.name || '--',
          pluginName: item.plugin_display_name || item.plugin_name || '其他',
        }))
        .filter((item: TemplateOption) => Number.isFinite(item.id));
      setTemplateOptions(options);
    } finally {
      setTemplateLoading(false);
    }
  };

  const submitCreate = async () => {
    const name = createName.trim();
    if (!name || selectedTemplateIds.length === 0) return;
    setCreateSaving(true);
    try {
      await createPolicyGroup({ name, template_ids: selectedTemplateIds });
      message.success('已创建策略组。实例尚未加入');
      setCreateOpen(false);
      await reloadFirstPage();
    } finally {
      setCreateSaving(false);
    }
  };

  const templateGroups = templateOptions.reduce((acc, item) => {
    const found = acc.find((group) => group.name === item.pluginName);
    if (found) found.items.push(item);
    else acc.push({ name: item.pluginName, items: [item] });
    return acc;
  }, [] as Array<{ name: string; items: TemplateOption[] }>);

  const columns: ColumnItem[] = [
    { title: t('common.name'), dataIndex: 'name', key: 'name' },
    {
      title: '默认',
      dataIndex: 'is_default',
      key: 'is_default',
      width: 90,
      render: (_, record) => (record.is_default ? <Tag color="blue">默认</Tag> : <span>--</span>),
    },
    {
      title: '规则',
      dataIndex: 'rules',
      key: 'rules',
      render: (_, record) => (
        <Button type="link" className="px-0" onClick={() => setRuleGroup(record as PolicyGroupRow)}>
          {(record.rules || []).length}
        </Button>
      ),
    },
    {
      title: '实例',
      dataIndex: 'member_count',
      key: 'member_count',
      width: 120,
      render: (_, record) => (
        <Button type="link" className="px-0" onClick={() => void openMembers(record as PolicyGroupRow)}>
          {record.member_count || 0}
        </Button>
      ),
    },
    {
      title: t('common.action'),
      dataIndex: 'action',
      key: 'action',
      width: 280,
      render: (_, record) => (
        <Permission requiredPermissions={['Edit']}>
          <Button
            type="link"
            disabled={Boolean(record.is_default)}
            onClick={() => void setDefaultPolicyGroup(Number(record.id)).then(() => loadGroups(objectId))}
          >
            默认
          </Button>
          <Button
            type="link"
            onClick={() => {
              setCopySource(record as PolicyGroupRow);
              setCopyName(`${record.name} 副本`);
            }}
          >
            复制
          </Button>
          <Popconfirm
            title="删除后，成员记为不自动入组，未恢复告警会结束。若这是默认组，之后新实例不再自动告警。"
            onConfirm={async () => {
              await deletePolicyGroup(Number(record.id));
              message.success(t('common.successfullyDeleted'));
              await loadGroups(objectId);
            }}
          >
            <Button type="link">{t('common.delete')}</Button>
          </Popconfirm>
        </Permission>
      ),
    },
  ];

  return (
    <Spin
      spinning={treeLoading}
      wrapperClassName="flex h-full min-h-0 w-full min-w-0 max-w-full flex-1 flex-col [&>.ant-spin-container]:flex [&>.ant-spin-container]:h-full [&>.ant-spin-container]:min-h-0 [&>.ant-spin-container]:flex-1 [&>.ant-spin-container]:flex-col"
    >
      <div className={assetStyle.asset}>
        <ResizableSidebar collapseStorageKey="monitor.event.policyGroup.sidebarCollapsed">
          <div className={assetStyle.assetTree}>
            <TreeSelector
              data={treeData}
              defaultSelectedKey={selectedKey}
              loading={treeLoading}
              onNodeSelect={(key) => {
                setObjectId(key);
                syncObjectId(key);
                setPagination((prev) => (prev.current === 1 ? prev : { ...prev, current: 1 }));
              }}
            />
          </div>
        </ResizableSidebar>
        <div className={assetStyle.table}>
          <div className={assetStyle.search}>
            <div className="min-w-0 flex-1">
              <Input
                className="w-full max-w-[320px]"
                placeholder={t('common.searchPlaceHolder')}
                allowClear
                value={searchText}
                onPressEnter={() => {
                  setAppliedSearch(searchText.trim());
                  setPagination((prev) => (prev.current === 1 ? prev : { ...prev, current: 1 }));
                }}
                onClear={() => {
                  setSearchText('');
                  setAppliedSearch('');
                  setPagination((prev) => (prev.current === 1 ? prev : { ...prev, current: 1 }));
                }}
                onChange={(event) => setSearchText(event.target.value)}
              />
            </div>
            <Permission requiredPermissions={['Edit']}>
              <Button type="primary" icon={<PlusOutlined />} disabled={!objectId} onClick={() => void openCreate()}>
                {t('common.add')}
              </Button>
            </Permission>
          </div>
          <div className="min-h-0 min-w-0 flex-1">
            <CustomTable
              rowKey="id"
              columns={columns}
              dataSource={groups}
              loading={loading}
              scroll={{ x: 'max-content' }}
              pagination={pagination}
              onChange={(next: Pagination) => {
                setPagination((prev) => ({
                  ...prev,
                  current: next.pageSize !== prev.pageSize ? 1 : next.current,
                  pageSize: next.pageSize || prev.pageSize,
                }));
              }}
            />
          </div>
        </div>
      </div>
      <Drawer
        title={memberGroup ? `${memberGroup.name} 的实例` : '实例'}
        open={Boolean(memberGroup)}
        width={760}
        onClose={() => {
          setMemberGroup(null);
          setMemberKeyword('');
          setJoinOpen(false);
        }}
      >
        <SearchActionBar
          searchProps={{
            placeholder: '搜索实例名称',
            value: memberKeyword,
            onChange: (event) => setMemberKeyword(event.target.value),
          }}
          actions={
            <Permission requiredPermissions={['Edit']}>
              <Button type="primary" disabled={!memberGroup} onClick={openJoin}>
                加入
              </Button>
            </Permission>
          }
        />
        <CustomTable
          rowKey="instance_id"
          loading={memberLoading}
          pagination={false}
          dataSource={members.filter((item) => {
            const keyword = memberKeyword.trim().toLowerCase();
            if (!keyword) return true;
            return String(item.name || '').toLowerCase().includes(keyword);
          })}
          columns={[
            { title: t('common.name'), dataIndex: 'name', key: 'name' },
            {
              title: '状态',
              dataIndex: 'state',
              key: 'state',
              width: 110,
              render: (_, record) => <Tag>{MEMBER_STATE[record.state] || record.state}</Tag>,
            },
            {
              title: '旧策略',
              dataIndex: 'legacy_policies',
              key: 'legacy_policies',
              render: (_, record) =>
                (record.legacy_policies || []).length ? (
                  <div className="flex flex-col gap-1">
                    {(record.legacy_policies || []).map((item: { id: number; name: string; enable: boolean }) => (
                      <span key={item.id}>
                        {item.name}
                        <span className="text-[var(--color-text-3)]">{item.enable ? ' · 仍会告警' : ' · 已停用'}</span>
                      </span>
                    ))}
                  </div>
                ) : (
                  '--'
                ),
            },
            {
              title: t('common.action'),
              key: 'action',
              width: 140,
              render: (_, record) => {
                const otherGroups = switchGroups.filter((item) => item.id !== memberGroup?.id);
                return (
                  <Permission requiredPermissions={['Edit']}>
                    <Dropdown
                      trigger={['click']}
                      menu={{
                        items: otherGroups.length
                          ? otherGroups.map((item) => ({ key: String(item.id), label: item.name }))
                          : [{ key: 'empty', label: '没有其他策略组', disabled: true }],
                        onClick: async ({ key }) => {
                          if (key === 'empty') return;
                          await joinPolicyGroup(Number(key), [record.instance_id]);
                          message.success('已更换，原规则未恢复告警会结束');
                          if (memberGroup) {
                            await openMembers(memberGroup);
                            await loadGroups(objectId);
                          }
                        },
                      }}
                    >
                      <Button type="link" className="px-0">
                        换组
                      </Button>
                    </Dropdown>
                    <Button
                      type="link"
                      onClick={async () => {
                        await leavePolicyGroup([record.instance_id]);
                        message.success('已退出，未恢复告警会结束');
                        if (memberGroup) {
                          await openMembers(memberGroup);
                          await loadGroups(objectId);
                        }
                      }}
                    >
                      退出
                    </Button>
                  </Permission>
                );
              },
            },
          ]}
        />
      </Drawer>
      <Modal
        title="加入实例"
        open={joinOpen}
        width={720}
        onCancel={() => setJoinOpen(false)}
        footer={
          <div>
            <Button className="mr-[10px]" type="primary" disabled={joinSelected.length === 0} onClick={() => void confirmJoin()}>
              加入
            </Button>
            <Button onClick={() => setJoinOpen(false)}>取消</Button>
          </div>
        }
      >
        <Input
          allowClear
          className="mb-3 w-80"
          placeholder="搜索实例名称"
          value={joinKeyword}
          onChange={(event) => setJoinKeyword(event.target.value)}
          onPressEnter={() => void loadJoinInstances(1, joinKeyword)}
          onClear={() => {
            setJoinKeyword('');
            void loadJoinInstances(1, '');
          }}
        />
        {joinSelected.length > 0 ? (
          <div className="mb-3 flex flex-wrap items-center gap-2">
            {joinSelected.map((id) => (
              <Tag
                key={id}
                closable
                onClose={(event) => {
                  event.preventDefault();
                  setJoinSelected((prev) => prev.filter((item) => item !== id));
                }}
              >
                {joinLabels[id] || id}
              </Tag>
            ))}
            <button type="button" className="cursor-pointer text-[var(--color-primary)]" onClick={() => setJoinSelected([])}>
              清空
            </button>
          </div>
        ) : null}
        <CustomTable
          rowKey="instance_id"
          loading={joinLoading}
          dataSource={joinRows}
          pagination={joinPagination}
          scroll={{ y: 'auto' }}
          rowSelection={{
            selectedRowKeys: joinSelected,
            onChange: (keys) => setJoinSelected(keys.map(String)),
            getCheckboxProps: (record: InstanceCandidate) => ({
              disabled: members.some((item) => String(item.instance_id) === String(record.instance_id)),
            }),
          }}
          onChange={(next: Pagination) => {
            void loadJoinInstances(
              next.pageSize !== joinPagination.pageSize ? 1 : next.current,
              joinKeyword,
              next.pageSize || joinPagination.pageSize
            );
          }}
          columns={[
            {
              title: t('common.name'),
              dataIndex: 'instance_name',
              key: 'instance_name',
              render: (_, record) => {
                const joined = members.some((item) => String(item.instance_id) === String(record.instance_id));
                return (
                  <span className="inline-flex items-center gap-2">
                    <span>{candidateLabel(record)}</span>
                    {joined ? <Tag>已在组</Tag> : null}
                  </span>
                );
              },
            },
          ]}
        />
      </Modal>
      <Modal
        title={ruleGroup ? `${ruleGroup.name} 的规则` : '规则'}
        open={Boolean(ruleGroup)}
        footer={null}
        onCancel={() => setRuleGroup(null)}
      >
        {(ruleGroup?.rules || []).map((item) => (
          <div key={item.id} className="mb-2 flex items-center justify-between">
            <span>
              {item.name}
              <span className="ml-2 text-[12px] text-[var(--color-text-3)]">{item.plugin_name}</span>
            </span>
            <Button
              type="link"
              onClick={() => {
                setRule(item);
                setThresholdDraft(cloneDeep(item.threshold || []) as ThresholdItem[]);
                setNoticeUsers(item.notice_users || []);
              }}
            >
              修改
            </Button>
          </div>
        ))}
      </Modal>
      <Modal
        title="新建策略组"
        open={createOpen}
        confirmLoading={createSaving}
        okText={t('common.confirm')}
        cancelText={t('common.cancel')}
        okButtonProps={{ disabled: !createName.trim() || selectedTemplateIds.length === 0 }}
        onCancel={() => {
          if (createSaving) return;
          setCreateOpen(false);
        }}
        onOk={() => void submitCreate()}
      >
        <div className="mb-3">
          <div className="mb-1">名称</div>
          <Input maxLength={100} value={createName} onChange={(event) => setCreateName(event.target.value)} />
        </div>
        <div>
          <div className="mb-1">策略模板</div>
          <Spin spinning={templateLoading}>
            <div className="max-h-[360px] overflow-y-auto">
              {templateGroups.length === 0 && !templateLoading ? (
                <span className="text-[var(--color-text-3)]">当前对象没有策略模板</span>
              ) : (
                templateGroups.map((group) => {
                  const ids = group.items.map((item) => item.id);
                  const selectedCount = ids.filter((id) => selectedTemplateIds.includes(id)).length;
                  return (
                    <div key={group.name} className="mb-3">
                      <Checkbox
                        checked={selectedCount === ids.length && ids.length > 0}
                        indeterminate={selectedCount > 0 && selectedCount < ids.length}
                        onChange={(event) => {
                          setSelectedTemplateIds((prev) =>
                            event.target.checked
                              ? Array.from(new Set([...prev, ...ids]))
                              : prev.filter((id) => !ids.includes(id))
                          );
                        }}
                      >
                        {group.name}
                      </Checkbox>
                      <div className="mt-1 flex flex-col gap-1 pl-6">
                        {group.items.map((item) => (
                          <Checkbox
                            key={item.id}
                            checked={selectedTemplateIds.includes(item.id)}
                            onChange={(event) => {
                              setSelectedTemplateIds((prev) =>
                                event.target.checked ? [...prev, item.id] : prev.filter((id) => id !== item.id)
                              );
                            }}
                          >
                            {item.name}
                          </Checkbox>
                        ))}
                      </div>
                    </div>
                  );
                })
              )}
            </div>
          </Spin>
        </div>
      </Modal>
      <Modal
        title="复制策略组"
        open={Boolean(copySource)}
        onCancel={() => setCopySource(null)}
        onOk={async () => {
          if (!copySource || !copyName.trim()) return;
          await copyPolicyGroup(copySource.id, copyName.trim());
          message.success('已复制。新组没有成员，也不是默认组');
          setCopySource(null);
          await loadGroups(objectId);
        }}
      >
        <Input value={copyName} onChange={(event) => setCopyName(event.target.value)} />
      </Modal>
      <Modal
        title={rule ? `修改 ${rule.name}` : '修改规则'}
        open={Boolean(rule)}
        onCancel={() => setRule(null)}
        onOk={async () => {
          if (!rule || !ruleGroup) return;
          await updatePolicyGroupRule({
            group_id: ruleGroup.id,
            rule_id: rule.id,
            threshold: thresholdDraft,
            notice_users: noticeUsers,
          });
          message.success('已修改当前规则，未恢复告警会结束');
          setRule(null);
          await loadGroups(objectId);
          setRuleGroup(null);
        }}
      >
        <div className="mb-3">
          <div className="mb-1">阈值</div>
          <ThresholdList
            data={thresholdDraft}
            onChange={setThresholdDraft}
            thresholdUnit={null}
            onThresholdUnitChange={() => undefined}
            showUnitSelector={false}
            allowStructureEdit
          />
        </div>
        <div>
          <div className="mb-1">通知人</div>
          <Select
            mode="multiple"
            className="w-full"
            value={noticeUsers}
            options={users.map((item) => ({ value: item.username, label: item.display_name || item.username }))}
            onChange={setNoticeUsers}
          />
        </div>
      </Modal>
    </Spin>
  );
};

export default PolicyGroupPage;
