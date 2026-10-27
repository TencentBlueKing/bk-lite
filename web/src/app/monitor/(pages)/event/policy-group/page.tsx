'use client';

import React, { useEffect, useRef, useState } from 'react';
import { Badge, Button, Checkbox, Drawer, Dropdown, Input, InputNumber, Modal, Popconfirm, Select, Spin, Switch, Tabs, Tag, Tooltip, message } from 'antd';
import { PlusOutlined } from '@ant-design/icons';
import SearchActionBar from '@/components/search-action-bar';
import { StatusToneBadge } from '@/app/monitor/utils/statusTone';
import { useRouter, useSearchParams } from 'next/navigation';
import useApiClient from '@/utils/request';
import useMonitorApi from '@/app/monitor/api';
import useIntegrationApi from '@/app/monitor/api/integration';
import useEventApi from '@/app/monitor/api/event';
import { useTranslation } from '@/utils/i18n';
import { buildMonitorStrategyDetailUrl } from '@/app/monitor/utils/policyRouteUtils';
import { ColumnItem, ObjectItem, Pagination, TableDataItem, TreeItem, UserItem } from '@/app/monitor/types';
import { findLabelById } from '@/app/monitor/utils/common';
import CustomTable from '@/components/custom-table';
import TreeSelector from '@/app/monitor/components/treeSelector';
import ResizableSidebar from '@/app/monitor/components/resizableSidebar';
import Permission from '@/components/permission';
import { useMonitorObjectQuery } from '@/app/monitor/hooks/useMonitorObjectQuery';
import { resolveMonitorObjectQueryId, resolveMonitorObjectTreeKey } from '@/app/monitor/utils/monitorObjectQuery';
import { buildMonitorObjectSidebarTree } from '@/app/monitor/utils/monitorObject';
import assetStyle from '../strategy/index.module.scss';
import SelectCard from '../strategy/detail/selectCard';
import { seedNoticeUsersFromHandlers, shouldRequireNoticeUsers } from '../strategy/detail/strategyDetailUtils';
import { buildPolicyGroupNoticePayload, policyGroupListBadges } from './policyGroupNotice';
import {
  DURATION_UNIT_OPTIONS,
  NO_DATA_LEVEL_OPTIONS,
  buildPolicyGroupDetectionPayload,
  defaultConfigTab,
  detectionConfirm,
  detectionDraftFromGroup,
  detectionSaveBlocker,
  durationBounds,
  policyGroupDetectionBadges,
  policyGroupDetectionNotes,
  type DetectionDraft,
  type PolicyGroupConfigTab,
} from './policyGroupDetection';
import { ChannelItem } from '@/app/monitor/types/event';
import { formatUserName } from '@/utils/userDisplay';
import { useUserInfoContext } from '@/context/userInfo';

interface PolicyGroupRule {
  id: number;
  name: string;
  plugin_name: string;
  threshold: Array<{ level?: string; method?: string; value?: number }>;
  query_type?: string;
  condition_thresholds?: Record<string, Array<{ level?: string; method?: string; value?: number | null }>>;
  alert_name?: string;
  trigger_count?: number;
  recovery_condition?: number;
  recovery_threshold?: { method?: string; value?: number | null };
  no_data_carrier?: boolean;
  policy_id?: number;
  open_alert_count?: number;
}

interface PolicyGroupRow {
  id: number;
  name: string;
  is_default?: boolean;
  member_count: number;
  rules: PolicyGroupRule[];
  notice?: boolean;
  notice_type?: string;
  notice_type_ids?: number[];
  notice_users?: Array<string | number>;
  notice_uniform?: boolean;
  handlers?: Array<string | number>;
  handlers_uniform?: boolean;
  enable?: boolean;
  enable_uniform?: boolean;
  schedule?: { type?: string; value?: number };
  schedule_uniform?: boolean;
  no_data?: {
    enabled?: boolean;
    period?: { type?: string; value?: number };
    level?: string;
    alert_name?: string;
    recovery_period?: { type?: string; value?: number };
  };
  no_data_uniform?: boolean;
  open_alert_count?: number;
}

interface TemplateOption {
  id: number;
  name: string;
  pluginName: string;
}

interface InstanceCandidate {
  instance_id?: string;
  instance_name?: string;
  id?: string;
  name?: string;
  ip?: string | null;
  summary_facts?: { 'asset.ip'?: string };
  policy_group_id?: number | null;
  policy_group_name?: string;
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

const CHANNEL_ICON: Record<string, string> = {
  email: 'youjian',
  enterprise_wechat_bot: 'qiwei2',
  feishu_bot: 'feishu',
  dingtalk_bot: 'dingding',
  custom_webhook: 'webhook',
  nats: 'dongzuo1',
};

const NAME_COLUMN_WIDTH = 162;
const COMPACT_COLUMN_WIDTH = 120;
const ACTION_COLUMN_WIDTH = 260;
const CONFIG_HINT_CLASS = 'text-xs leading-5 text-[var(--color-text-3)]';

const noticeSnapshot = (
  enabled: boolean,
  typeIds: number[],
  userIds: string[],
  handlers: string[]
) => JSON.stringify({ enabled, typeIds, userIds, handlers });

const CHANNEL_TYPE_KEY: Record<string, string> = {
  email: 'monitor.events.channelTypeEmail',
  enterprise_wechat_bot: 'monitor.events.channelTypeWechatBot',
  feishu_bot: 'monitor.events.channelTypeFeishuBot',
  dingtalk_bot: 'monitor.events.channelTypeDingtalkBot',
  custom_webhook: 'monitor.events.channelTypeCustomWebhook',
  nats: 'monitor.events.channelTypeNats',
};

const PolicyGroupPage: React.FC = () => {
  const { t } = useTranslation();
  const router = useRouter();
  const { isLoading } = useApiClient();
  const { getMonitorObject, getInstanceList, getAllUsers } = useMonitorApi();
  const {
    getPolicyGroups,
    getPolicyGroupMembers,
    getPolicyGroupInstanceGroups,
    joinPolicyGroup,
    leavePolicyGroup,
    updatePolicyGroupDetection,
    updatePolicyGroupNotice,
    updatePolicyGroupEnable,
    copyPolicyGroup,
    setDefaultPolicyGroup,
    deletePolicyGroup,
    createPolicyGroup,
  } = useIntegrationApi();
  const { getPolicyTemplate, getSystemChannelList } = useEventApi();
  const currentGroupId = useUserInfoContext()?.selectedGroup?.id;
  const searchParams = useSearchParams();
  const { syncObjectId } = useMonitorObjectQuery();
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
  const [enableSavingId, setEnableSavingId] = useState<number | null>(null);
  const [templateLoading, setTemplateLoading] = useState(false);
  const [templateOptions, setTemplateOptions] = useState<TemplateOption[]>([]);
  const [selectedTemplateIds, setSelectedTemplateIds] = useState<number[]>([]);
  const [memberGroup, setMemberGroup] = useState<PolicyGroupRow | null>(null);
  const [members, setMembers] = useState<TableDataItem[]>([]);
  const [memberLoading, setMemberLoading] = useState(false);
  const [memberKeyword, setMemberKeyword] = useState('');
  const [memberPagination, setMemberPagination] = useState<Pagination>({
    current: 1,
    total: 0,
    pageSize: 10,
  });
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
  const [rulePagination, setRulePagination] = useState<Pagination>({
    current: 1,
    total: 0,
    pageSize: 10,
  });
  const openedRuleList = useRef(false);
  const [configGroup, setConfigGroup] = useState<PolicyGroupRow | null>(null);
  const [configTab, setConfigTab] = useState<PolicyGroupConfigTab>('detection');
  const [detectionInitial, setDetectionInitial] = useState<DetectionDraft>(() => detectionDraftFromGroup({}));
  const [detectionDraft, setDetectionDraft] = useState<DetectionDraft>(() => detectionDraftFromGroup({}));
  const [detectionSaving, setDetectionSaving] = useState(false);
  const noticeInitial = useRef('');
  const [noticeEnabled, setNoticeEnabled] = useState(false);
  const [noticeTypeIds, setNoticeTypeIds] = useState<number[]>([]);
  const [noticeUserIds, setNoticeUserIds] = useState<string[]>([]);
  const [handlerIds, setHandlerIds] = useState<string[]>([]);
  const noticeUsersSeeded = useRef(false);
  const [noticeChannels, setNoticeChannels] = useState<ChannelItem[]>([]);
  const [noticeUserOptions, setNoticeUserOptions] = useState<UserItem[]>([]);
  const [noticeLoading, setNoticeLoading] = useState(false);
  const [noticeSaving, setNoticeSaving] = useState(false);
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
        create_default: false,
      });
      const items = Array.isArray(data) ? data : data?.items || [];
      const total = Array.isArray(data) ? items.length : Number(data?.count || 0);
      if (page > 1 && items.length === 0 && total > 0) {
        setPagination((prev) => ({ ...prev, current: page - 1, total }));
        return;
      }
      setGroups(items);
      setPagination((prev) => ({ ...prev, current: page, pageSize, total }));
      return items as PolicyGroupRow[];
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    if (isLoading) return;
    setTreeLoading(true);
    getMonitorObject({ add_instance_count: true })
      .then((data: ObjectItem[]) => {
        const tree = buildMonitorObjectSidebarTree(data, (item) => ({
          title: item.display_name || item.name || '--',
          label: item.name || '--',
          key: item.id,
          icon: item.icon,
          children: [],
        }));
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

  useEffect(() => {
    if (openedRuleList.current || searchParams.get('rules') !== '1') return;
    const targetId = searchParams.get('groupId');
    if (!targetId) return;
    const group = groups.find((item) => String(item.id) === targetId);
    if (!group) return;
    openedRuleList.current = true;
    setRulePagination((prev) => ({ ...prev, current: 1 }));
    setRuleGroup(group);
  }, [groups, searchParams]);

  const openMembers = async (group: PolicyGroupRow) => {
    setMemberGroup(group);
    setMemberKeyword('');
    setMemberPagination((prev) => ({ ...prev, current: 1 }));
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
      const ids = results.map((item) => String(item.instance_id || item.id || '')).filter(Boolean);
      const grouped = ids.length ? await getPolicyGroupInstanceGroups(ids) : [];
      const groupByInstance = new Map(
        (Array.isArray(grouped) ? grouped : []).map((item: { instance_id?: string; group_id?: number; group_name?: string }) => [
          String(item.instance_id || ''),
          item,
        ])
      );
      const rows = results.map((item) => {
        const hit = groupByInstance.get(String(item.instance_id || item.id || ''));
        return {
          ...item,
          policy_group_id: hit?.group_id ?? null,
          policy_group_name: hit?.group_name || '',
        };
      });
      setJoinRows(rows);
      setJoinLabels((prev) => {
        const next = { ...prev };
        rows.forEach((item) => {
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

  const loadNotice = (group: PolicyGroupRow) => {
    noticeUsersSeeded.current = false;
    const enabled = Boolean(group.notice);
    const typeIds = (group.notice_type_ids || []).map((item) => Number(item));
    let userIds = (group.notice_users || []).map((item) => String(item));
    let handlers = (group.handlers || []).map((item) => String(item));
    setNoticeEnabled(enabled);
    setNoticeTypeIds(typeIds);
    setNoticeUserIds(userIds);
    setHandlerIds(handlers);
    noticeInitial.current = noticeSnapshot(enabled, typeIds, userIds, handlers);
    setNoticeLoading(true);
    Promise.all([
      getSystemChannelList(),
      currentGroupId ? getAllUsers([currentGroupId]) : getAllUsers(),
    ])
      .then(([channels, userList]) => {
        const nextChannels = Array.isArray(channels) ? channels : [];
        const nextUsers = Array.isArray(userList) ? userList : [];
        setNoticeChannels(nextChannels);
        setNoticeUserOptions(nextUsers);
        const matchUserId = (value: string) => {
          const matched = nextUsers.find(
            (item) => String(item.id) === value || item.username === value
          );
          return matched ? String(matched.id) : value;
        };
        userIds = userIds.map(matchUserId);
        handlers = handlers.map(matchUserId);
        setNoticeUserIds(userIds);
        setHandlerIds(handlers);
        noticeInitial.current = noticeSnapshot(enabled, typeIds, userIds, handlers);
      })
      .finally(() => setNoticeLoading(false));
  };

  const noticeDirty = () =>
    noticeSnapshot(noticeEnabled, noticeTypeIds, noticeUserIds, handlerIds) !== noticeInitial.current;

  const detectionDirty = () => JSON.stringify(detectionDraft) !== JSON.stringify(detectionInitial);

  const noticeUsersRequired = shouldRequireNoticeUsers({
    notice: noticeEnabled,
    noticeTypeIds,
    channelList: noticeChannels,
  });

  useEffect(() => {
    if (!configGroup || !noticeUsersRequired) {
      noticeUsersSeeded.current = false;
      return;
    }
    if (noticeUsersSeeded.current) return;
    const seeded = seedNoticeUsersFromHandlers(noticeUserIds, handlerIds);
    noticeUsersSeeded.current = true;
    if (seeded) {
      setNoticeUserIds(seeded.map((item) => String(item)));
    }
  }, [handlerIds, configGroup, noticeUserIds, noticeUsersRequired]);

  const submitNotice = async (group: PolicyGroupRow) => {
    const selectedChannels = noticeChannels.filter((item) => noticeTypeIds.includes(item.id));
    setNoticeSaving(true);
    try {
      await updatePolicyGroupNotice(
        buildPolicyGroupNoticePayload({
          groupId: group.id,
          noticeEnabled,
          noticeType: selectedChannels[0]?.channel_type || '',
          noticeTypeIds,
          noticeUsersRequired,
          noticeUserIds,
          handlerIds,
        })
      );
      message.success('已写入这一组的全部规则');
      setConfigGroup(null);
      await loadGroups(objectId);
    } finally {
      setNoticeSaving(false);
    }
  };

  // 两页各自保存。另一页改了没存的，只提醒，不一起写入。
  const saveNotice = () => {
    if (!configGroup || noticeSaving) return;
    const group = configGroup;
    if (!detectionDirty()) {
      void submitNotice(group);
      return;
    }
    Modal.confirm({
      title: '保存响应配置',
      content: '检测页有未保存的改动，这次不会一起写入。',
      onOk: () => submitNotice(group),
    });
  };

  const detectionScope = {
    scheduleUniform: configGroup?.schedule_uniform,
    noDataUniform: configGroup?.no_data_uniform,
    initial: detectionInitial,
  };

  const loadDetection = (group: PolicyGroupRow) => {
    const next = detectionDraftFromGroup(group, {
      scheduleUniform: group.schedule_uniform,
      noDataUniform: group.no_data_uniform,
    });
    setDetectionInitial(next);
    setDetectionDraft(next);
  };

  const openConfig = (group: PolicyGroupRow, tab?: PolicyGroupConfigTab) => {
    loadDetection(group);
    loadNotice(group);
    setConfigTab(
      tab ||
        defaultConfigTab(
          policyGroupDetectionBadges({
            scheduleUniform: group.schedule_uniform,
            noDataUniform: group.no_data_uniform,
          }),
          policyGroupListBadges({
            notice: group.notice,
            noticeUniform: group.notice_uniform,
            noticeTypeIds: group.notice_type_ids,
            handlersUniform: group.handlers_uniform,
          })
        )
    );
    setConfigGroup(group);
  };

  const closeConfig = () => {
    if (detectionSaving || noticeSaving) return;
    setConfigGroup(null);
  };

  const patchDetection = (patch: Partial<DetectionDraft>) => {
    setDetectionDraft((current) => ({ ...current, ...patch }));
  };

  const saveDetection = () => {
    if (!configGroup || detectionSaving) return;
    const blocker = detectionSaveBlocker(detectionDraft, detectionScope);
    if (blocker) {
      message.warning(blocker);
      return;
    }
    const payload = buildPolicyGroupDetectionPayload(configGroup.id, detectionDraft, detectionScope);
    const confirm = detectionConfirm(payload, detectionInitial);
    const noticePending = noticeDirty() ? '响应页有未保存的改动，这次不会一起写入。' : '';
    Modal.confirm({
      title: confirm.title,
      content: `${confirm.content}${noticePending}`,
      onOk: async () => {
        setDetectionSaving(true);
        try {
          await updatePolicyGroupDetection(payload);
          message.success('已写入这一组的检测配置');
          setConfigGroup(null);
          await loadGroups(objectId);
        } finally {
          setDetectionSaving(false);
        }
      },
    });
  };

  const submitGroupEnable = async (record: PolicyGroupRow, enable: boolean) => {
    if (enableSavingId != null) return;
    setEnableSavingId(record.id);
    try {
      await updatePolicyGroupEnable(record.id, enable);
      message.success(enable ? '已生效，从现在开始扫描' : '已停用，未恢复告警会结束');
      await loadGroups(objectId);
    } finally {
      setEnableSavingId(null);
    }
  };

  const changeGroupEnable = (record: PolicyGroupRow, enable: boolean) => {
    if (enableSavingId != null) return;
    if (enable) {
      void submitGroupEnable(record, true);
      return;
    }
    const count = record.open_alert_count || 0;
    Modal.confirm({
      title: '停用策略组',
      content: `停用后停止扫描，并结束 ${count} 条未恢复告警。成员仍留在组里。`,
      onOk: () => submitGroupEnable(record, false),
    });
  };

  const templateGroups = templateOptions.reduce((acc, item) => {
    const found = acc.find((group) => group.name === item.pluginName);
    if (found) found.items.push(item);
    else acc.push({ name: item.pluginName, items: [item] });
    return acc;
  }, [] as Array<{ name: string; items: TemplateOption[] }>);

  const columns: ColumnItem[] = [
    {
      title: t('common.name'),
      dataIndex: 'name',
      key: 'name',
      width: NAME_COLUMN_WIDTH,
      render: (_, record) => {
        const badges = [
          ...policyGroupListBadges({
            notice: record.notice,
            noticeUniform: record.notice_uniform,
            noticeTypeIds: record.notice_type_ids,
            handlersUniform: record.handlers_uniform,
          }),
          ...policyGroupDetectionBadges({
            scheduleUniform: record.schedule_uniform,
            noDataUniform: record.no_data_uniform,
          }),
        ];
        return (
          <span className="inline-flex min-w-0 flex-wrap items-center gap-2">
            <span>{record.name}</span>
            {badges.map((label) => (
              <StatusToneBadge key={label} tone="warning" label={label} />
            ))}
          </span>
        );
      },
    },
    {
      title: '默认',
      dataIndex: 'is_default',
      key: 'is_default',
      width: COMPACT_COLUMN_WIDTH,
      render: (_, record) => (record.is_default ? <StatusToneBadge tone="primary" label="默认" /> : <span>--</span>),
    },
    {
      title: '规则',
      dataIndex: 'rules',
      key: 'rules',
      width: COMPACT_COLUMN_WIDTH,
      render: (_, record) => (
        <Button
          type="link"
          className="px-0"
          onClick={() => {
            setRulePagination((prev) => ({ ...prev, current: 1 }));
            setRuleGroup(record as PolicyGroupRow);
          }}
        >
          {(record.rules || []).length}
        </Button>
      ),
    },
    {
      title: '实例',
      dataIndex: 'member_count',
      key: 'member_count',
      width: COMPACT_COLUMN_WIDTH,
      render: (_, record) => (
        <Button type="link" className="px-0" onClick={() => void openMembers(record as PolicyGroupRow)}>
          {record.member_count || 0}
        </Button>
      ),
    },
    {
      title: t('monitor.events.effective'),
      dataIndex: 'enable',
      key: 'enable',
      width: COMPACT_COLUMN_WIDTH,
      render: (_, record) => {
        const mixed = record.enable_uniform === false;
        const control = (
          <Switch
            size="small"
            loading={enableSavingId === record.id}
            checked={Boolean(record.enable)}
            onChange={(value) => changeGroupEnable(record as PolicyGroupRow, value)}
          />
        );
        return (
          <Permission requiredPermissions={['Edit']}>
            {mixed ? <Tooltip title="组内规则的生效不一致，切换后会写成同一套">{control}</Tooltip> : control}
          </Permission>
        );
      },
    },
    {
      title: t('common.action'),
      dataIndex: 'action',
      key: 'action',
      width: ACTION_COLUMN_WIDTH,
      fixed: 'right',
      render: (_, record) => (
        <Permission requiredPermissions={['Edit']}>
          <Button
            type="link"
            className="px-0"
            disabled={Boolean(record.is_default)}
            onClick={() => void setDefaultPolicyGroup(Number(record.id)).then(() => loadGroups(objectId))}
          >
            默认
          </Button>
          <Button type="link" onClick={() => openConfig(record as PolicyGroupRow)}>
            配置
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
            title={`删除后，成员记为不自动入组，将结束 ${record.open_alert_count || 0} 条未恢复告警。若这是默认组，之后新实例不再自动告警。`}
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

  const memberKeywordText = memberKeyword.trim().toLowerCase();
  const filteredMembers = members.filter((item) => {
    if (!memberKeywordText) return true;
    return String(item.name || '').toLowerCase().includes(memberKeywordText);
  });
  const visibleMembers = filteredMembers.slice(
    (memberPagination.current - 1) * memberPagination.pageSize,
    memberPagination.current * memberPagination.pageSize
  );
  const ruleRows = ruleGroup?.rules || [];
  const visibleRules = ruleRows.slice(
    (rulePagination.current - 1) * rulePagination.pageSize,
    rulePagination.current * rulePagination.pageSize
  );

  return (
    <div className="flex h-full min-h-0 w-full min-w-0 max-w-full flex-1 flex-col">
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
          <SearchActionBar
            searchProps={{
              placeholder: t('common.searchPlaceHolder'),
              allowClear: true,
              value: searchText,
              onPressEnter: () => {
                setAppliedSearch(searchText.trim());
                setPagination((prev) => (prev.current === 1 ? prev : { ...prev, current: 1 }));
              },
              onSearch: () => {
                setAppliedSearch(searchText.trim());
                setPagination((prev) => (prev.current === 1 ? prev : { ...prev, current: 1 }));
              },
              onClear: () => {
                setSearchText('');
                setAppliedSearch('');
                setPagination((prev) => (prev.current === 1 ? prev : { ...prev, current: 1 }));
              },
              onChange: (event) => setSearchText(event.target.value),
            }}
            actions={(
              <Permission requiredPermissions={['Edit']}>
                <Button type="primary" icon={<PlusOutlined />} disabled={!objectId} onClick={() => void openCreate()}>
                  {t('common.new')}
                </Button>
              </Permission>
            )}
          />
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
        title={joinOpen ? '加入实例' : memberGroup ? `${memberGroup.name} 的实例` : '实例'}
        open={Boolean(memberGroup)}
        width={600}
        closable={false}
        onClose={() => {
          setMemberGroup(null);
          setMemberKeyword('');
          setJoinOpen(false);
        }}
        footer={
          joinOpen ? (
            <div className="flex justify-end gap-2">
              <Button type="primary" disabled={joinSelected.length === 0} onClick={() => void confirmJoin()}>
                加入
              </Button>
              <Button
                onClick={() => {
                  setJoinOpen(false);
                  setJoinSelected([]);
                }}
              >
                取消
              </Button>
            </div>
          ) : null
        }
      >
        {joinOpen ? (
          <>
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
                  render: (_, record) => candidateLabel(record),
                },
                {
                  title: '所属策略组',
                  dataIndex: 'policy_group_name',
                  key: 'policy_group_name',
                  width: 180,
                  render: (_, record) => {
                    const joinedHere = members.some((item) => String(item.instance_id) === String(record.instance_id));
                    if (joinedHere) return <Tag>已在组</Tag>;
                    if (!record.policy_group_name) {
                      return <span className="text-[var(--color-text-3)]">未加入</span>;
                    }
                    const text = `已在 ${record.policy_group_name}`;
                    return (
                      <span className="block min-w-0 truncate" title={text}>
                        {text}
                      </span>
                    );
                  },
                },
              ]}
            />
          </>
        ) : (
          <>
        <SearchActionBar
          searchProps={{
            placeholder: '搜索实例名称',
            value: memberKeyword,
            onChange: (event) => {
              setMemberKeyword(event.target.value);
              setMemberPagination((prev) => ({ ...prev, current: 1 }));
            },
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
          pagination={{ ...memberPagination, total: filteredMembers.length }}
          onChange={(next: Pagination) => {
            setMemberPagination((prev) => ({
              ...prev,
              current: next.pageSize !== prev.pageSize ? 1 : next.current,
              pageSize: next.pageSize || prev.pageSize,
            }));
          }}
          dataSource={visibleMembers}
          scroll={{ y: 'auto' }}
          columns={[
            { title: t('common.name'), dataIndex: 'name', key: 'name' },
            {
              title: t('common.action'),
              key: 'action',
              width: 120,
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
          </>
        )}
      </Drawer>
      <Drawer
        title={ruleGroup ? `${ruleGroup.name} 的规则` : '规则'}
        open={Boolean(ruleGroup)}
        width={760}
        closable={false}
        onClose={() => {
          setRuleGroup(null);
        }}
      >
          <CustomTable
            rowKey="id"
            dataSource={visibleRules}
            pagination={{ ...rulePagination, total: ruleRows.length }}
            scroll={{ y: 'auto' }}
            onChange={(next: Pagination) => {
              setRulePagination((prev) => ({
                ...prev,
                current: next.pageSize !== prev.pageSize ? 1 : next.current,
                pageSize: next.pageSize || prev.pageSize,
              }));
            }}
            columns={[
              {
                title: t('common.name'),
                dataIndex: 'name',
                key: 'name',
                render: (_, record) => (
                  <span className="inline-flex flex-wrap items-center gap-2">
                    <span>{record.name}</span>
                    {record.no_data_carrier ? <StatusToneBadge tone="neutral" label="承载无数据" /> : null}
                  </span>
                ),
              },
              {
                title: '模板',
                dataIndex: 'plugin_name',
                key: 'plugin_name',
                width: 160,
                render: (_, record) => record.plugin_name || '--',
              },
              {
                title: t('common.action'),
                key: 'action',
                width: 90,
                render: (_, record) => (
                  <Button
                    type="link"
                    className="px-0"
                    onClick={() => {
                      if (!ruleGroup || !objectId) return;
                      router.push(
                        buildMonitorStrategyDetailUrl('groupRule', {
                          monitorObjId: String(objectId),
                          monitorName: findLabelById(treeData, String(objectId)) || '',
                          id: record.policy_id,
                          name: record.name,
                          groupId: ruleGroup.id,
                          ruleId: record.id,
                        })
                      );
                    }}
                  >
                    修改
                  </Button>
                ),
              },
            ]}
          />
      </Drawer>
      <Drawer
        title={configGroup ? `${configGroup.name} 的配置` : '配置'}
        open={Boolean(configGroup)}
        width={760}
        closable={false}
        onClose={closeConfig}
        footer={
          <div className="flex justify-end gap-2">
            {configTab === 'detection' ? (
              <Button
                type="primary"
                loading={detectionSaving}
                disabled={Boolean(detectionSaveBlocker(detectionDraft, detectionScope))}
                onClick={saveDetection}
              >
                确认
              </Button>
            ) : (
              <Button
                type="primary"
                loading={noticeSaving}
                disabled={
                  noticeLoading ||
                  (noticeEnabled && noticeTypeIds.length === 0) ||
                  (noticeUsersRequired && noticeUserIds.length === 0)
                }
                onClick={saveNotice}
              >
                确认
              </Button>
            )}
            <Button disabled={detectionSaving || noticeSaving} onClick={closeConfig}>
              取消
            </Button>
          </div>
        }
      >
        {(() => {
          const detectionBadges = policyGroupDetectionBadges({
            scheduleUniform: configGroup?.schedule_uniform,
            noDataUniform: configGroup?.no_data_uniform,
          });
          const noticeBadges = policyGroupListBadges({
            notice: configGroup?.notice,
            noticeUniform: configGroup?.notice_uniform,
            noticeTypeIds: configGroup?.notice_type_ids,
            handlersUniform: configGroup?.handlers_uniform,
          });
          const tabLabel = (label: string, badges: string[]) =>
            badges.length ? (
              <Tooltip title={badges.join('、')}>
                <Badge dot offset={[4, 0]}>
                  {label}
                </Badge>
              </Tooltip>
            ) : (
              label
            );
          return (
            <Tabs
              activeKey={configTab}
              onChange={(key) => setConfigTab(key as PolicyGroupConfigTab)}
              items={[
                { key: 'detection', label: tabLabel('检测', detectionBadges) },
                { key: 'notice', label: tabLabel('响应', noticeBadges) },
              ]}
            />
          );
        })()}
        {configTab === 'detection' ? (() => {
          const notes = policyGroupDetectionNotes({
            scheduleUniform: configGroup?.schedule_uniform,
            noDataUniform: configGroup?.no_data_uniform,
          });
          const scheduleNote = notes.find((note) => note.includes('检测频率'));
          const noDataNote = notes.find((note) => note.includes('无数据'));
          const detectionBlocker = detectionSaveBlocker(detectionDraft, detectionScope);
          const alertNameError = detectionBlocker === '请填写无数据告警名称'
            ? t('common.required')
            : detectionBlocker === '无数据告警名称过长'
              ? detectionBlocker
              : null;
          const detectionHint = alertNameError ? null : detectionBlocker;
          return (
            <>
        <div className={`mb-3 ${CONFIG_HINT_CLASS}`}>
          一台成员停止上报时，每个插件只产生一条告警。
        </div>
        <div className="mb-3">
          <div className="mb-1">检测频率</div>
          {scheduleNote ? <div className={`mb-1 ${CONFIG_HINT_CLASS}`}>{scheduleNote}</div> : null}
          <div className="flex items-center gap-2">
            <InputNumber
              className="w-[160px]"
              min={durationBounds(detectionDraft.scheduleUnit).min}
              max={durationBounds(detectionDraft.scheduleUnit).max}
              precision={0}
              value={detectionDraft.scheduleValue}
              onChange={(value) => patchDetection({ scheduleValue: typeof value === 'number' ? value : null })}
            />
            <Select
              className="w-[120px]"
              value={detectionDraft.scheduleUnit}
              options={[...DURATION_UNIT_OPTIONS]}
              onChange={(unit) => {
                const bounds = durationBounds(unit);
                const next = detectionDraft.scheduleValue;
                patchDetection({
                  scheduleUnit: unit,
                  scheduleValue: next == null || next < bounds.min || next > bounds.max ? null : next,
                });
              }}
            />
          </div>
          <div className={`mt-[10px] ${CONFIG_HINT_CLASS}`}>多久查一次。汇聚周期仍按各规则的模板。</div>
        </div>
        <div className="mb-3">
          <div className="mb-1">无数据告警</div>
          {noDataNote ? <div className={`mb-1 ${CONFIG_HINT_CLASS}`}>{noDataNote}</div> : null}
          {detectionDraft.noDataEnabled == null ? (
            <Select
              className="w-[160px]"
              placeholder="请选择"
              options={[
                { value: 'on', label: '开启' },
                { value: 'off', label: '关闭' },
              ]}
              onChange={(value) => patchDetection({ noDataEnabled: value === 'on' })}
            />
          ) : (
            <Switch
              checked={detectionDraft.noDataEnabled}
              onChange={(checked) => patchDetection({ noDataEnabled: checked })}
            />
          )}
          <div className={`mt-[10px] ${CONFIG_HINT_CLASS}`}>查不到数据时告警。</div>
        </div>
        {detectionDraft.noDataEnabled ? (
          <>
            <div className="mb-3">
              <div className="mb-1">
                <span className="mr-1 text-[var(--color-error)]" aria-hidden="true">*</span>
                告警名称
              </div>
              <Input
                className="w-[360px]"
                status={alertNameError ? 'error' : undefined}
                value={detectionDraft.noDataAlertName}
                onChange={(event) => patchDetection({ noDataAlertName: event.target.value })}
              />
              {alertNameError ? (
                <div className="mt-1 text-[var(--color-error)]">{alertNameError}</div>
              ) : null}
              <div className={`mt-[10px] ${CONFIG_HINT_CLASS}`}>例如：主机无数据</div>
            </div>
            <div className="mb-3">
              <div className="mb-1">检测窗</div>
              <div className="flex items-center gap-2">
                <InputNumber
                  className="w-[160px]"
                  min={1}
                  max={Math.max(durationBounds(detectionDraft.noDataPeriodUnit).max, detectionDraft.noDataPeriodValue)}
                  precision={0}
                  value={detectionDraft.noDataPeriodValue}
                  onChange={(value) => {
                    if (typeof value === 'number') patchDetection({ noDataPeriodValue: value });
                  }}
                />
                <Select
                  className="w-[120px]"
                  value={detectionDraft.noDataPeriodUnit}
                  options={[...DURATION_UNIT_OPTIONS]}
                  onChange={(unit) => {
                    const bounds = durationBounds(unit);
                    const next = detectionDraft.noDataPeriodValue;
                    patchDetection({
                      noDataPeriodUnit: unit,
                      noDataPeriodValue: next < bounds.min || next > bounds.max ? bounds.min : next,
                    });
                  }}
                />
              </div>
              <div className={`mt-[10px] ${CONFIG_HINT_CLASS}`}>连续查不到这么久才告警。</div>
            </div>
            <div className="mb-3">
              <div className="mb-1">级别</div>
              <Select
                className="w-[160px]"
                value={detectionDraft.noDataLevel}
                options={[...NO_DATA_LEVEL_OPTIONS]}
                onChange={(level) => patchDetection({ noDataLevel: level })}
              />
            </div>
            <div className="mb-3">
              <div className="mb-1">恢复窗</div>
              <div className="flex items-center gap-2">
                <InputNumber
                  className="w-[160px]"
                  min={1}
                  max={Math.max(durationBounds(detectionDraft.noDataRecoveryUnit).max, detectionDraft.noDataRecoveryValue)}
                  precision={0}
                  value={detectionDraft.noDataRecoveryValue}
                  onChange={(value) => {
                    if (typeof value === 'number') patchDetection({ noDataRecoveryValue: value });
                  }}
                />
                <Select
                  className="w-[120px]"
                  value={detectionDraft.noDataRecoveryUnit}
                  options={[...DURATION_UNIT_OPTIONS]}
                  onChange={(unit) => {
                    const bounds = durationBounds(unit);
                    const next = detectionDraft.noDataRecoveryValue;
                    patchDetection({
                      noDataRecoveryUnit: unit,
                      noDataRecoveryValue: next < bounds.min || next > bounds.max ? bounds.min : next,
                    });
                  }}
                />
              </div>
              <div className={`mt-[10px] ${CONFIG_HINT_CLASS}`}>数据回来并持续这么久才恢复，不能长于检测窗。</div>
            </div>
          </>
        ) : null}
        {detectionHint ? (
          <div className="text-[var(--color-text-3)]">{detectionHint}</div>
        ) : null}
            </>
          );
        })() : (
        <Spin spinning={noticeLoading}>
          {configGroup?.notice_uniform === false ? (
            <div className={`mb-3 ${CONFIG_HINT_CLASS}`}>组内规则的通知不一致，保存后会写成同一套。</div>
          ) : null}
          {configGroup?.handlers_uniform === false ? (
            <div className={`mb-3 ${CONFIG_HINT_CLASS}`}>组内规则的处理人不一致，保存后会写成同一套。</div>
          ) : null}
          <div className="mb-3">
            <div className="mb-1">处理人</div>
            <Select
              mode="multiple"
              className="w-[360px]"
              showSearch
              allowClear
              optionFilterProp="label"
              value={handlerIds}
              options={noticeUserOptions.map((item) => ({
                value: String(item.id),
                label: formatUserName(item),
              }))}
              onChange={setHandlerIds}
            />
            <div className={`mt-[10px] ${CONFIG_HINT_CLASS}`}>
              新告警带上这些处理人，正在响的告警不变。
            </div>
          </div>
          <div className="mb-3">
            <div className="mb-1">通知</div>
            <Switch checked={noticeEnabled} onChange={setNoticeEnabled} />
            <div className={`mt-[10px] ${CONFIG_HINT_CLASS}`}>写入本组全部规则，不结束正在告警的事件。</div>
          </div>
          {noticeEnabled ? (
            <>
              <div className="mb-3">
                <div className="mb-1">通知方式</div>
                {noticeChannels.length ? (
                  <SelectCard
                    data={noticeChannels.map((item) => ({
                      icon: CHANNEL_ICON[item.channel_type] || 'jiqiren3',
                      title: item.name,
                      tag: CHANNEL_TYPE_KEY[item.channel_type] ? t(CHANNEL_TYPE_KEY[item.channel_type]) : item.channel_type,
                      description: item.description,
                      value: item.id,
                    }))}
                    value={noticeTypeIds}
                    onChange={(ids) => setNoticeTypeIds(ids.map((item) => Number(item)))}
                  />
                ) : (
                  <span className="text-[var(--color-text-3)]">还没有可用的通知方式</span>
                )}
              </div>
              {noticeUsersRequired ? (
                <div>
                  <div className="mb-1">通知人</div>
                  <Select
                    mode="multiple"
                    className="w-[360px]"
                    showSearch
                    optionFilterProp="label"
                    value={noticeUserIds}
                    options={noticeUserOptions.map((item) => ({
                      value: String(item.id),
                      label: formatUserName(item),
                    }))}
                    onChange={setNoticeUserIds}
                  />
                </div>
              ) : null}
            </>
          ) : null}
        </Spin>
        )}
      </Drawer>
      <Drawer
        title="新建策略组"
        open={createOpen}
        width={760}
        closable={false}
        onClose={() => {
          if (createSaving) return;
          setCreateOpen(false);
        }}
        footer={
          <div className="flex justify-end gap-2">
            <Button
              type="primary"
              loading={createSaving}
              disabled={!createName.trim() || selectedTemplateIds.length === 0}
              onClick={() => void submitCreate()}
            >
              确认
            </Button>
            <Button disabled={createSaving} onClick={() => setCreateOpen(false)}>
              取消
            </Button>
          </div>
        }
      >
        <div className="mb-3">
          <div className="mb-1">名称</div>
          <Input maxLength={100} value={createName} onChange={(event) => setCreateName(event.target.value)} />
        </div>
        <div>
          <div className="mb-1">策略模板</div>
          <Spin spinning={templateLoading}>
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
          </Spin>
        </div>
      </Drawer>
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
    </div>
  );
};

export default PolicyGroupPage;
