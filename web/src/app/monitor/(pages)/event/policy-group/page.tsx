'use client';

import React, { useEffect, useState } from 'react';
import { Button, Drawer, Input, InputNumber, Modal, Popconfirm, Select, Spin, Tag, message } from 'antd';
import { useSearchParams } from 'next/navigation';
import { cloneDeep } from 'lodash';
import useApiClient from '@/utils/request';
import useMonitorApi from '@/app/monitor/api';
import useIntegrationApi from '@/app/monitor/api/integration';
import useEventApi from '@/app/monitor/api/event';
import { useTranslation } from '@/utils/i18n';
import { ColumnItem, ObjectItem, TableDataItem, TreeItem, UserItem } from '@/app/monitor/types';
import CustomTable from '@/components/custom-table';
import TreeSelector from '@/app/monitor/components/treeSelector';
import ResizableSidebar from '@/app/monitor/components/resizableSidebar';
import Permission from '@/components/permission';
import { useCommon } from '@/app/monitor/context/common';
import { useMonitorObjectQuery } from '@/app/monitor/hooks/useMonitorObjectQuery';
import { resolveMonitorObjectQueryId, resolveMonitorObjectTreeKey } from '@/app/monitor/utils/monitorObjectQuery';
import assetStyle from '../strategy/index.module.scss';

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

const MEMBER_STATE: Record<string, string> = {
  member: '在组',
  declined: '不自动入组',
  skipped: '未入组',
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
  } = useIntegrationApi();
  const { patchMonitorPolicy } = useEventApi();
  const searchParams = useSearchParams();
  const { syncObjectId } = useMonitorObjectQuery();
  const users: UserItem[] = useCommon()?.userList || [];
  const [treeLoading, setTreeLoading] = useState(false);
  const [treeData, setTreeData] = useState<TreeItem[]>([]);
  const [selectedKey, setSelectedKey] = useState('');
  const [objectId, setObjectId] = useState<React.Key>('');
  const [groups, setGroups] = useState<PolicyGroupRow[]>([]);
  const [loading, setLoading] = useState(false);
  const [memberGroup, setMemberGroup] = useState<PolicyGroupRow | null>(null);
  const [members, setMembers] = useState<TableDataItem[]>([]);
  const [memberLoading, setMemberLoading] = useState(false);
  const [candidateIds, setCandidateIds] = useState<string[]>([]);
  const [candidates, setCandidates] = useState<Array<{ value: string; label: string }>>([]);
  const [ruleGroup, setRuleGroup] = useState<PolicyGroupRow | null>(null);
  const [rule, setRule] = useState<PolicyGroupRule | null>(null);
  const [thresholdValue, setThresholdValue] = useState<number | null>(null);
  const [noticeUsers, setNoticeUsers] = useState<string[]>([]);

  const loadGroups = async (id: React.Key) => {
    setLoading(true);
    try {
      const data = await getPolicyGroups({ monitor_object_id: id });
      setGroups(Array.isArray(data) ? data : []);
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
  }, [objectId]);

  const openMembers = async (group: PolicyGroupRow) => {
    setMemberGroup(group);
    setMemberLoading(true);
    setCandidateIds([]);
    try {
      const [memberRows, instancePage] = await Promise.all([
        getPolicyGroupMembers(group.id),
        getInstanceList(objectId, { page: 1, page_size: 100 }),
      ]);
      setMembers(Array.isArray(memberRows) ? memberRows : []);
      const results = instancePage?.results || instancePage?.items || [];
      setCandidates(
        results.map((item: { id?: string; instance_id?: string; name?: string }) => ({
          value: String(item.id || item.instance_id),
          label: item.name || String(item.id || item.instance_id),
        }))
      );
    } finally {
      setMemberLoading(false);
    }
  };

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
      title: '已加入实例',
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
          <Button type="link" onClick={() => void setDefaultPolicyGroup(Number(record.id)).then(() => loadGroups(objectId))}>
            设为默认
          </Button>
          <Button
            type="link"
            onClick={() => {
              let name = `${record.name} 副本`;
              Modal.confirm({
                title: '复制策略组',
                content: (
                  <Input
                    defaultValue={name}
                    onChange={(event) => {
                      name = event.target.value;
                    }}
                  />
                ),
                onOk: async () => {
                  await copyPolicyGroup(Number(record.id), name);
                  message.success('已复制。新组没有成员，也不是默认组');
                  await loadGroups(objectId);
                },
              });
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
    <Spin spinning={treeLoading} wrapperClassName="flex h-full min-h-0 w-full flex-1 flex-col">
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
              }}
            />
          </div>
        </ResizableSidebar>
        <div className={assetStyle.table}>
          <CustomTable rowKey="id" columns={columns} dataSource={groups} loading={loading} pagination={false} />
        </div>
      </div>
      <Drawer title={memberGroup ? `${memberGroup.name} 的实例` : '实例'} open={Boolean(memberGroup)} width={720} onClose={() => setMemberGroup(null)}>
        <Permission requiredPermissions={['Edit']}>
          <div className="mb-3 flex gap-2">
            <Select
              mode="multiple"
              className="min-w-0 flex-1"
              placeholder="选择已接入实例加入这一组"
              value={candidateIds}
              options={candidates}
              onChange={setCandidateIds}
            />
            <Button
              type="primary"
              disabled={!memberGroup || candidateIds.length === 0}
              onClick={async () => {
                if (!memberGroup) return;
                await joinPolicyGroup(memberGroup.id, candidateIds);
                message.success('已加入。已在其他组的实例会先离开原组');
                setCandidateIds([]);
                await openMembers(memberGroup);
                await loadGroups(objectId);
              }}
            >
              加入
            </Button>
          </div>
        </Permission>
        <CustomTable
          rowKey="instance_id"
          loading={memberLoading}
          pagination={false}
          dataSource={members}
          columns={[
            { title: t('common.name'), dataIndex: 'name', key: 'name' },
            {
              title: '状态',
              dataIndex: 'state',
              key: 'state',
              render: (_, record) => MEMBER_STATE[record.state] || record.state,
            },
            {
              title: '旧策略',
              dataIndex: 'legacy_policies',
              key: 'legacy_policies',
              render: (_, record) =>
                (record.legacy_policies || []).length ? (
                  (record.legacy_policies || []).map((item: { id: number; name: string; enable: boolean }) => (
                    <div key={item.id}>
                      {item.name}
                      {item.enable ? ' · 仍会一起告警' : ' · 已停用'}
                      {item.enable ? (
                        <Button
                          type="link"
                          onClick={async () => {
                            await patchMonitorPolicy(item.id, { enable: false });
                            if (memberGroup) await openMembers(memberGroup);
                          }}
                        >
                          停用
                        </Button>
                      ) : null}
                    </div>
                  ))
                ) : (
                  '--'
                ),
            },
            {
              title: t('common.action'),
              key: 'action',
              render: (_, record) => (
                <Permission requiredPermissions={['Edit']}>
                  <Select
                    className="mr-2 w-[160px]"
                    placeholder="换到其他组"
                    options={groups
                      .filter((item) => item.id !== memberGroup?.id)
                      .map((item) => ({ value: item.id, label: item.name }))}
                    onChange={async (value) => {
                      await joinPolicyGroup(value, [record.instance_id]);
                      message.success('已更换，原规则未恢复告警会结束');
                      if (memberGroup) {
                        await openMembers(memberGroup);
                        await loadGroups(objectId);
                      }
                    }}
                  />
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
              ),
            },
          ]}
        />
      </Drawer>
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
                setThresholdValue(item.threshold?.[0]?.value ?? null);
                setNoticeUsers(item.notice_users || []);
              }}
            >
              修改
            </Button>
          </div>
        ))}
      </Modal>
      <Modal
        title={rule ? `修改 ${rule.name}` : '修改规则'}
        open={Boolean(rule)}
        onCancel={() => setRule(null)}
        onOk={async () => {
          if (!rule || !ruleGroup) return;
          const nextThreshold = cloneDeep(rule.threshold || []);
          if (nextThreshold[0]) nextThreshold[0].value = thresholdValue ?? nextThreshold[0].value;
          await updatePolicyGroupRule({
            group_id: ruleGroup.id,
            rule_id: rule.id,
            threshold: nextThreshold,
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
          <InputNumber className="w-full" value={thresholdValue} onChange={(value) => setThresholdValue(typeof value === 'number' ? value : null)} />
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
