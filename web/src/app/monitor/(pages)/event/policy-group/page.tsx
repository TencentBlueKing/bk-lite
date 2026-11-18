'use client';

import React, { useEffect, useRef, useState } from 'react';
import Cookies from 'js-cookie';
import { Alert, Button, Checkbox, Drawer, Dropdown, Input, InputNumber, Modal, Pagination as AntPagination, Popconfirm, Popover, Segmented, Select, Spin, Switch, Tag, Tooltip, message } from 'antd';
import { PlusOutlined } from '@ant-design/icons';
import SearchActionBar from '@/components/search-action-bar';
import ToolbarSplitShell from '@/components/toolbar-split-shell';
import { StatusToneBadge } from '@/app/monitor/utils/statusTone';
import Link from 'next/link';
import { useRouter, useSearchParams } from 'next/navigation';
import useApiClient from '@/utils/request';
import useMonitorApi from '@/app/monitor/api';
import useIntegrationApi from '@/app/monitor/api/integration';
import useEventApi from '@/app/monitor/api/event';
import { useTranslation } from '@/utils/i18n';
import { buildMonitorStrategyDetailUrl } from '@/app/monitor/utils/policyRouteUtils';
import { ColumnItem, ObjectItem, Pagination, TreeItem, UserItem } from '@/app/monitor/types';
import { findLabelById } from '@/app/monitor/utils/common';
import CustomTable from '@/components/custom-table';
import TreeSelector from '@/app/monitor/components/treeSelector';
import ResizableSidebar from '@/app/monitor/components/resizableSidebar';
import Permission from '@/components/permission';
import { CURRENT_TEAM_COOKIE } from '@/utils/userTeamPreference';
import {
  candidateBelongsToOtherOrganization,
  joinCandidateCheckboxDisabled,
  joinCandidateGroupLabel,
} from './joinCandidate';
import { appliedPolicyGroupSearch, policyGroupListEmptyText } from './policyGroupListEmpty';
import { useMonitorObjectQuery } from '@/app/monitor/hooks/useMonitorObjectQuery';
import { MODULE_OBJECT_QUERY_PARAM, resolveMonitorObjectQueryId, resolveMonitorObjectTreeKey } from '@/app/monitor/utils/monitorObjectQuery';
import { buildMonitorObjectSidebarTree } from '@/app/monitor/utils/monitorObject';
import assetStyle from '../strategy/index.module.scss';
import SelectCard from '../strategy/detail/selectCard';
import { seedNoticeUsersFromHandlers, shouldRequireNoticeUsers } from '../strategy/detail/strategyDetailUtils';
import { buildPolicyGroupNoticePayload, policyGroupListBadges } from './policyGroupNotice';
import {
  DURATION_UNIT_OPTIONS,
  buildPolicyGroupDetectionPayload,
  detectionDraftFromGroup,
  durationBounds,
  policyGroupDetectionBadges,
  policyGroupDetectionNotes,
  type DetectionDraft,
} from './policyGroupDetection';
import { ChannelItem } from '@/app/monitor/types/event';
import { formatUserName } from '@/utils/userDisplay';
import { useUserInfoContext } from '@/context/userInfo';
import { useUnitTransform } from '@/app/monitor/hooks/useUnitTransform';
import {
  VIEW_MODE_OPTIONS,
  buildPolicyGroupRuleColumns,
  diffGroupTemplates,
  filterAndSortRules,
  filterPolicyGroupMembers,
  memberTemplateFilterOptions,
  pluginCounts,
  renderPluginTag,
  rulesForTemplateIds,
  templateIdsFromRules,
  type PolicyGroupMember,
  type PolicyGroupMemberTemplate,
  type PolicyGroupRule,
} from './policyGroupRuleView';

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
  organization?: Array<string | number>;
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
    setPolicyGroupTemplates,
  } = useIntegrationApi();
  const { getPolicyTemplate, getSystemChannelList } = useEventApi();
  const currentGroupId = useUserInfoContext()?.selectedGroup?.id;
  const { findUnitNameById } = useUnitTransform();
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
  const [defaultRemoved, setDefaultRemoved] = useState(false);
  const [createOpen, setCreateOpen] = useState(false);
  const [createName, setCreateName] = useState('');
  const [createSaving, setCreateSaving] = useState(false);
  const [adjustingGroup, setAdjustingGroup] = useState<PolicyGroupRow | null>(null);
  const [enableSavingId, setEnableSavingId] = useState<number | null>(null);
  const [templateLoading, setTemplateLoading] = useState(false);
  const [templateOptions, setTemplateOptions] = useState<TemplateOption[]>([]);
  const [selectedTemplateIds, setSelectedTemplateIds] = useState<number[]>([]);
  const [memberGroup, setMemberGroup] = useState<PolicyGroupRow | null>(null);
  const [members, setMembers] = useState<PolicyGroupMember[]>([]);
  const [memberTemplateFilter, setMemberTemplateFilter] = useState<string | null>(null);
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
  const [viewMode, setViewMode] = useState<'workbench' | 'groupList'>('workbench');
  const [selectedGroupId, setSelectedGroupId] = useState<number | null>(null);
  const [workbenchKeyword, setWorkbenchKeyword] = useState('');
  const [workbenchPluginFilter, setWorkbenchPluginFilter] = useState('all');
  const [workbenchNoData, setWorkbenchNoData] = useState<'on' | 'off' | null>(null);
  const [workbenchPagination, setWorkbenchPagination] = useState<Pagination>({
    current: 1,
    total: 0,
    pageSize: 15,
  });

  const [ruleGroup, setRuleGroup] = useState<PolicyGroupRow | null>(null);
  const [ruleKeyword, setRuleKeyword] = useState('');
  const [ruleNoData, setRuleNoData] = useState<'on' | 'off' | null>(null);
  const [rulePluginFilter, setRulePluginFilter] = useState<string>('all');
  const [rulePagination, setRulePagination] = useState<Pagination>({
    current: 1,
    total: 0,
    pageSize: 10,
  });
  const openedRuleList = useRef(false);
  const [configGroup, setConfigGroup] = useState<PolicyGroupRow | null>(null);
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
      setDefaultRemoved(Boolean(!Array.isArray(data) && data?.default_removed));
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

  const openRuleList = (group: PolicyGroupRow) => {
    setRuleKeyword('');
    setRuleNoData(null);
    setRulePagination((prev) => ({ ...prev, current: 1 }));
    setRuleGroup(group);
  };

  const initializedUrlGroup = useRef(false);

  useEffect(() => {
    if (groups.length === 0) return;
    if (!initializedUrlGroup.current) {
      const targetId = searchParams.get('groupId');
      if (targetId && groups.some((item) => String(item.id) === targetId)) {
        initializedUrlGroup.current = true;
        setSelectedGroupId(Number(targetId));
        if (!openedRuleList.current && searchParams.get('rules') === '1') {
          openedRuleList.current = true;
          const targetGroup = groups.find((item) => String(item.id) === targetId);
          if (targetGroup) openRuleList(targetGroup);
        }
        return;
      }
    }
    if (!selectedGroupId || !groups.some((g) => g.id === selectedGroupId)) {
      const defaultGroup = groups.find((g) => g.is_default);
      setSelectedGroupId(defaultGroup ? defaultGroup.id : groups[0].id);
    }
  }, [groups, searchParams, selectedGroupId]);

  const openMembers = async (group: PolicyGroupRow) => {
    setMemberGroup(group);
    setMemberKeyword('');
    setMemberTemplateFilter(null);
    setMemberPagination((prev) => ({ ...prev, current: 1 }));
    setMemberLoading(true);
    try {
      const [memberRows, allGroups] = await Promise.all([
        getPolicyGroupMembers(group.id),
        getPolicyGroups({ monitor_object_id: objectId, create_default: false }),
      ]);
      setMembers(Array.isArray(memberRows) ? (memberRows as PolicyGroupMember[]) : []);
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

  const loadTemplateOptions = async () => {
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

  const openCreate = async () => {
    setAdjustingGroup(null);
    setCreateOpen(true);
    setCreateName('新建策略组');
    setSelectedTemplateIds([]);
    await loadTemplateOptions();
  };

  const openAdjustRules = async (group: PolicyGroupRow) => {
    setAdjustingGroup(group);
    setCreateOpen(true);
    setCreateName(group.name);
    setSelectedTemplateIds(templateIdsFromRules(group.rules || []));
    await loadTemplateOptions();
  };

  const saveAdjust = async () => {
    if (!adjustingGroup) return;
    const targetId = adjustingGroup.id;
    setCreateSaving(true);
    try {
      const result = await setPolicyGroupTemplates({
        group_id: targetId,
        template_ids: selectedTemplateIds,
      });
      const added = Number(result?.added || 0);
      const removed = Number(result?.removed || 0);
      if (added > 0 && removed > 0) {
        message.success(`已调整策略：新增 ${added} 条，移除 ${removed} 条`);
      } else if (added > 0) {
        message.success(`已新增 ${added} 条策略，按接入插件匹配到的实例开始扫描`);
      } else if (removed > 0) {
        message.success(`已从策略组移除 ${removed} 条策略`);
      } else {
        message.info('策略没有变化');
      }
      setCreateOpen(false);
      setAdjustingGroup(null);
      const items = await loadGroups(objectId);
      const next = (items || []).find((item) => item.id === targetId);
      if (next && ruleGroup?.id === targetId) setRuleGroup(next);
    } finally {
      setCreateSaving(false);
    }
  };

  const submitCreate = async () => {
    if (adjustingGroup) {
      const existingIds = templateIdsFromRules(adjustingGroup.rules || []);
      const { addedIds, removedIds } = diffGroupTemplates(existingIds, selectedTemplateIds);
      if (addedIds.length === 0 && removedIds.length === 0) {
        message.info('策略没有变化');
        setCreateOpen(false);
        setAdjustingGroup(null);
        return;
      }
      if (removedIds.length > 0) {
        const removedRules = rulesForTemplateIds(adjustingGroup.rules || [], removedIds);
        const alertCount = removedRules.reduce((sum, rule) => sum + (rule.open_alert_count || 0), 0);
        Modal.confirm({
          title: '确认移除策略',
          zIndex: 1100,
          content: (
            <div>
              <p>将从本策略组移除以下策略。对应扫描会停止，未恢复告警会结束。策略模板本身不会删除。</p>
              <ul className="mb-0 mt-2 pl-5">
                {removedRules.map((rule) => (
                  <li key={rule.id}>
                    {rule.name}
                    {rule.open_alert_count ? `（${rule.open_alert_count} 条未恢复告警）` : ''}
                  </li>
                ))}
              </ul>
              {alertCount > 0 ? <p className="mb-0 mt-2">合计结束 {alertCount} 条未恢复告警。</p> : null}
            </div>
          ),
          okText: '确认移除并保存',
          cancelText: '返回修改',
          okButtonProps: { danger: true },
          onOk: () => saveAdjust(),
        });
        return;
      }
      await saveAdjust();
      return;
    }
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

  const saveConfig = async () => {
    if (!configGroup || detectionSaving || noticeSaving) return;
    const group = configGroup;
    setDetectionSaving(true);
    setNoticeSaving(true);
    try {
      const cleanDetectionDraft = {
        ...detectionDraft,
        noDataEnabled: false,
      };
      const detectionPayload = buildPolicyGroupDetectionPayload(group.id, cleanDetectionDraft, detectionScope);
      const selectedChannels = noticeChannels.filter((item) => noticeTypeIds.includes(item.id));
      const noticePayload = buildPolicyGroupNoticePayload({
        groupId: group.id,
        noticeEnabled,
        noticeType: selectedChannels[0]?.channel_type || '',
        noticeTypeIds,
        noticeUsersRequired,
        noticeUserIds,
        handlerIds,
      });

      await Promise.all([
        updatePolicyGroupDetection(detectionPayload),
        updatePolicyGroupNotice(noticePayload),
      ]);
      message.success('已保存策略组配置');
      setConfigGroup(null);
      await loadGroups(objectId);
    } catch (e: any) {
      message.error(e?.message || '保存失败');
    } finally {
      setDetectionSaving(false);
      setNoticeSaving(false);
    }
  };

  const openConfig = (group: PolicyGroupRow) => {
    loadDetection(group);
    loadNotice(group);
    setConfigGroup(group);
  };

  const closeConfig = () => {
    if (detectionSaving || noticeSaving) return;
    setConfigGroup(null);
  };

  const patchDetection = (patch: Partial<DetectionDraft>) => {
    setDetectionDraft((current) => ({ ...current, ...patch }));
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
      width: 130,
      render: (_, record) => {
        const rules = record.rules || [];
        const pluginCounts: Record<string, number> = {};
        rules.forEach((r) => {
          const name = r.plugin_name || '其他';
          pluginCounts[name] = (pluginCounts[name] || 0) + 1;
        });
        const pluginEntries = Object.entries(pluginCounts);
        const content = (
          <div className="inline-flex flex-col">
            <Button
              type="link"
              className="px-0 w-fit"
              onClick={() => openRuleList(record as PolicyGroupRow)}
            >
              {rules.length}
            </Button>
            {pluginEntries.length > 1 && (
              <span className="text-[12px] leading-4 text-[var(--color-text-3)]">
                {pluginEntries.length} 类模板
              </span>
            )}
          </div>
        );
        if (pluginEntries.length <= 1) return content;
        return (
          <Popover
            trigger="hover"
            placement="topLeft"
            mouseEnterDelay={0.12}
            mouseLeaveDelay={0.1}
            getPopupContainer={() => document.body}
            styles={{ body: { padding: 0, borderRadius: 8 } }}
            content={
              <div className="w-[240px]">
                <div className="border-b border-[var(--color-border-2)] bg-[var(--color-fill-1)] px-3 py-2 text-xs font-medium text-[var(--color-text-1)]">
                  涵盖监控模板分布
                </div>
                <div className="space-y-1.5 px-3 py-2">
                  {pluginEntries.map(([name, count]) => (
                    <div key={name} className="flex items-center justify-between gap-4 text-xs">
                      <span className="min-w-0 truncate text-[var(--color-text-1)]">{name}</span>
                      <span className="shrink-0 font-mono tabular-nums text-[var(--color-text-2)]">{count} 条</span>
                    </div>
                  ))}
                </div>
                <div className="border-t border-[var(--color-border-1)] px-3 py-2 text-[11px] leading-4 text-[var(--color-text-3)]">
                  主机接入时按其对应协议匹配生效，其余规则静默
                </div>
              </div>
            }
          >
            {content}
          </Popover>
        );
      },
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

  const filteredMembers = filterPolicyGroupMembers(members, {
    keyword: memberKeyword,
    filter: memberTemplateFilter,
  });
  const visibleMembers = filteredMembers.slice(
    (memberPagination.current - 1) * memberPagination.pageSize,
    memberPagination.current * memberPagination.pageSize
  );
  const ruleRows = ruleGroup?.rules || [];
  const availablePlugins = React.useMemo(() => pluginCounts(ruleRows), [ruleRows]);
  const filteredRules = React.useMemo(
    () =>
      filterAndSortRules(ruleRows, {
        pluginFilter: rulePluginFilter,
        noData: ruleNoData,
        keyword: ruleKeyword,
      }),
    [ruleRows, rulePluginFilter, ruleNoData, ruleKeyword]
  );
  const visibleRules = filteredRules.slice(
    (rulePagination.current - 1) * rulePagination.pageSize,
    rulePagination.current * rulePagination.pageSize
  );
  const listEmptyText = policyGroupListEmptyText({
    objectSelected: Boolean(objectId),
    search: appliedSearch,
    defaultRemoved,
  });
  const joinCandidateState = (record: InstanceCandidate) => {
    const belongsToOtherOrganization = candidateBelongsToOtherOrganization(
      record.organization,
      Cookies.get(CURRENT_TEAM_COOKIE)
    );
    const joinedHere = members.some((item) => String(item.instance_id) === String(record.instance_id));
    return {
      belongsToOtherOrganization,
      joinedHere,
      label: joinCandidateGroupLabel({
        belongsToOtherOrganization,
        policyGroupName: record.policy_group_name,
        joinedHere,
      }),
    };
  };

  const currentGroup = groups.find((g) => g.id === selectedGroupId) || groups[0] || null;
  const currentGroupRules = currentGroup?.rules || [];
  const availableWorkbenchPlugins = React.useMemo(
    () => pluginCounts(currentGroupRules),
    [currentGroupRules]
  );
  const filteredWorkbenchRules = React.useMemo(
    () =>
      filterAndSortRules(currentGroupRules, {
        pluginFilter: workbenchPluginFilter,
        noData: workbenchNoData,
        keyword: workbenchKeyword,
      }),
    [currentGroupRules, workbenchKeyword, workbenchPluginFilter, workbenchNoData]
  );
  const visibleWorkbenchRules = React.useMemo(() => {
    const start = (workbenchPagination.current - 1) * workbenchPagination.pageSize;
    return filteredWorkbenchRules.slice(start, start + workbenchPagination.pageSize);
  }, [filteredWorkbenchRules, workbenchPagination]);

  const openRuleEditor = (group: PolicyGroupRow | null, record: PolicyGroupRule) => {
    if (!group || !objectId) return;
    router.push(
      buildMonitorStrategyDetailUrl('groupRule', {
        monitorObjId: String(objectId),
        monitorName: findLabelById(treeData, String(objectId)) || '',
        id: record.policy_id,
        name: record.name,
        groupId: group.id,
        ruleId: record.id,
      })
    );
  };

  const workbenchColumns = React.useMemo(
    () =>
      buildPolicyGroupRuleColumns({
        t,
        unitLabel: findUnitNameById,
        noDataFilter: workbenchNoData,
        nameClassName: 'font-medium text-[var(--color-text-1)]',
        onEdit: (record) => openRuleEditor(currentGroup, record),
      }),
    [t, findUnitNameById, workbenchNoData, currentGroup, objectId, treeData]
  );
  const drawerRuleColumns = React.useMemo(
    () =>
      buildPolicyGroupRuleColumns({
        t,
        unitLabel: findUnitNameById,
        noDataFilter: ruleNoData,
        onEdit: (record) => openRuleEditor(ruleGroup, record),
      }),
    [t, findUnitNameById, ruleNoData, ruleGroup, objectId, treeData]
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
          {viewMode === 'workbench' && currentGroup ? (
            <div className="flex h-full min-h-0 w-full flex-col overflow-hidden">
              {/* 标准工具条：左侧视图与策略组选择，右侧搜索与操作成组 */}
              <div className="mb-3 flex flex-wrap items-center justify-between gap-x-4 gap-y-2">
                <div className="flex flex-wrap items-center gap-2">
                  <Segmented
                    value={viewMode}
                    onChange={(val) => setViewMode(val as 'workbench' | 'groupList')}
                    options={[...VIEW_MODE_OPTIONS]}
                  />
                  {groups.length > 1 ? (
                    <Select
                      value={currentGroup.id}
                      onChange={(val) => {
                        setSelectedGroupId(val);
                        setWorkbenchPluginFilter('all');
                        setWorkbenchPagination((prev) => ({ ...prev, current: 1 }));
                      }}
                      className="w-56"
                      options={groups.map((g) => ({
                        label: `${g.name}${g.is_default ? ' (默认)' : ''}`,
                        value: g.id,
                      }))}
                    />
                  ) : (
                    <span className="text-[13px] font-semibold text-[var(--color-text-1)]">
                      {currentGroup.name}
                    </span>
                  )}
                  {currentGroup.is_default ? (
                    <StatusToneBadge tone="primary" label="默认" />
                  ) : (
                    <Permission requiredPermissions={['Edit']}>
                      <Button
                        type="link"
                        size="small"
                        className="px-0 text-xs"
                        onClick={() => void setDefaultPolicyGroup(Number(currentGroup.id)).then(() => loadGroups(objectId))}
                      >
                        设为默认
                      </Button>
                    </Permission>
                  )}
                </div>

                <div className="flex items-center gap-2">
                  <Input
                    allowClear
                    placeholder="搜索规则名称或模板"
                    value={workbenchKeyword}
                    className="w-60"
                    onChange={(event) => {
                      setWorkbenchKeyword(event.target.value);
                      setWorkbenchPagination((prev) => ({ ...prev, current: 1 }));
                    }}
                    onClear={() => {
                      setWorkbenchKeyword('');
                      setWorkbenchPagination((prev) => ({ ...prev, current: 1 }));
                    }}
                  />
                  <Button onClick={() => openConfig(currentGroup)}>
                    配置
                  </Button>
                  <Permission requiredPermissions={['Edit']}>
                    <Button onClick={() => void openAdjustRules(currentGroup)}>
                      调整策略
                    </Button>
                  </Permission>
                  <Button
                    onClick={() => {
                      setCopySource(currentGroup);
                      setCopyName(`${currentGroup.name} 副本`);
                    }}
                  >
                    复制
                  </Button>
                  <Permission requiredPermissions={['Edit']}>
                    <Popconfirm
                      title={`删除后，成员记为不自动入组，将结束 ${currentGroup.open_alert_count || 0} 条未恢复告警。若这是默认组，之后新实例不再自动告警。`}
                      onConfirm={async () => {
                        await deletePolicyGroup(Number(currentGroup.id));
                        message.success(t('common.successfullyDeleted'));
                        setSelectedGroupId(null);
                        await loadGroups(objectId);
                      }}
                    >
                      <Button danger>
                        删除
                      </Button>
                    </Popconfirm>
                  </Permission>
                  <Permission requiredPermissions={['Edit']}>
                    <Button type="primary" icon={<PlusOutlined />} disabled={!objectId} onClick={() => void openCreate()}>
                      {t('common.new')}
                    </Button>
                  </Permission>
                </div>
              </div>

              {/* 策略组轻量属性行 */}
              <div className="mb-2 flex flex-wrap items-center justify-between gap-2 border-b border-[var(--color-border-1)] pb-2 text-[12px] text-[var(--color-text-3)]">
                <div className="flex items-center gap-4">
                  <div className="flex items-center gap-1.5">
                    <span>生效数量:</span>
                    <Button
                      type="link"
                      size="small"
                      className="px-0 font-medium"
                      onClick={() => void openMembers(currentGroup)}
                    >
                      {currentGroup.member_count || 0} 台
                    </Button>
                  </div>
                  <div className="flex items-center gap-1.5">
                    <span>生效状态:</span>
                    <Permission requiredPermissions={['Edit']}>
                      <Switch
                        size="small"
                        loading={enableSavingId === currentGroup.id}
                        checked={Boolean(currentGroup.enable)}
                        onChange={(val) => changeGroupEnable(currentGroup, val)}
                      />
                    </Permission>
                  </div>
                </div>

                {availableWorkbenchPlugins.length > 1 && (
                  <div className="flex flex-wrap items-center gap-1.5 text-xs">
                    <span className="text-[var(--color-text-3)] mr-0.5">接入模板:</span>
                    <Tag.CheckableTag
                      checked={workbenchPluginFilter === 'all'}
                      onChange={() => {
                        setWorkbenchPluginFilter('all');
                        setWorkbenchPagination((prev) => ({ ...prev, current: 1 }));
                      }}
                    >
                      全部 ({currentGroupRules.length}条规则)
                    </Tag.CheckableTag>
                    {availableWorkbenchPlugins.map(({ name }) => (
                      <Tag.CheckableTag
                        key={name}
                        checked={workbenchPluginFilter === name}
                        onChange={() => {
                          setWorkbenchPluginFilter(name);
                          setWorkbenchPagination((prev) => ({ ...prev, current: 1 }));
                        }}
                      >
                        {name}
                      </Tag.CheckableTag>
                    ))}
                  </div>
                )}
              </div>

              {/* 规则清单表格与底部固定分页 */}
              <div className="min-h-0 min-w-0 flex-1 flex flex-col justify-between overflow-hidden">
                <div className="min-h-0 min-w-0 flex-1 overflow-auto">
                  <CustomTable
                    rowKey="id"
                    columns={workbenchColumns}
                    dataSource={visibleWorkbenchRules}
                    loading={loading}
                    pagination={false}
                    onChange={(_pagination, filters) => {
                      const selected = filters?.no_data_enabled;
                      const value = Array.isArray(selected) && selected.length ? String(selected[0]) : '';
                      setWorkbenchNoData(value === 'on' || value === 'off' ? value : null);
                      setWorkbenchPagination((prev) => ({
                        ...prev,
                        current: 1,
                      }));
                    }}
                  />
                </div>
                <div className="mt-2.5 flex items-center justify-between border-t border-[var(--color-border-1)] pt-2.5 shrink-0 text-xs">
                  <span className="text-[var(--color-text-3)] font-medium">
                    共 {filteredWorkbenchRules.length} 条规则
                  </span>
                  <AntPagination
                    size="small"
                    current={workbenchPagination.current}
                    pageSize={workbenchPagination.pageSize}
                    total={filteredWorkbenchRules.length}
                    showSizeChanger
                    pageSizeOptions={['10', '15', '20', '50']}
                    showQuickJumper
                    onChange={(page, pageSize) => {
                      setWorkbenchPagination((prev) => ({
                        ...prev,
                        current: pageSize !== prev.pageSize ? 1 : page,
                        pageSize,
                      }));
                    }}
                  />
                </div>
              </div>
            </div>
          ) : (
            <div className="flex h-full min-h-0 w-full flex-col overflow-hidden">
              <ToolbarSplitShell
                leading={
                  groups.length > 0 ? (
                    <Segmented
                      value={viewMode}
                      onChange={(val) => setViewMode(val as 'workbench' | 'groupList')}
                      options={[...VIEW_MODE_OPTIONS]}
                    />
                  ) : undefined
                }
                trailing={(
                  <>
                    <Input.Search
                      placeholder={t('common.searchPlaceHolder')}
                      allowClear
                      enterButton
                      className="w-60"
                      value={searchText}
                      onSearch={(value) => {
                        const next = appliedPolicyGroupSearch(value);
                        setSearchText(next);
                        setAppliedSearch(next);
                        setPagination((prev) => (prev.current === 1 ? prev : { ...prev, current: 1 }));
                      }}
                      onChange={(event) => setSearchText(event.target.value)}
                    />
                    <Permission requiredPermissions={['Edit']}>
                      <Button type="primary" icon={<PlusOutlined />} disabled={!objectId} onClick={() => void openCreate()}>
                        {t('common.new')}
                      </Button>
                    </Permission>
                  </>
                )}
              />
              <div className="min-h-0 min-w-0 flex-1">
                <CustomTable
                  rowKey="id"
                  columns={columns}
                  dataSource={groups}
                  loading={loading}
                  scroll={{ x: 'max-content' }}
                  locale={listEmptyText ? { emptyText: <span className="text-[var(--color-text-3)]">{listEmptyText}</span> } : undefined}
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
          )}
        </div>
      </div>
      <Drawer
        title={joinOpen ? '加入实例' : memberGroup ? `${memberGroup.name} 的实例` : '实例'}
        open={Boolean(memberGroup)}
        width={joinOpen ? 600 : 760}
        closable={false}
        onClose={() => {
          setMemberGroup(null);
          setMemberKeyword('');
          setMemberTemplateFilter(null);
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
                onChange: (keys) => {
                  const blocked = new Set(
                    joinRows
                      .filter((row) => joinCandidateCheckboxDisabled(joinCandidateState(row)))
                      .map((row) => String(row.instance_id || row.id || ''))
                  );
                  setJoinSelected(keys.map(String).filter((id) => !blocked.has(id)));
                },
                getCheckboxProps: (record: InstanceCandidate) => ({
                  disabled: joinCandidateCheckboxDisabled(joinCandidateState(record)),
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
                    const { label } = joinCandidateState(record);
                    if (label.kind === 'joined-here') return <Tag>已在组</Tag>;
                    if (label.kind === 'empty' || label.kind === 'other-empty') {
                      return <span className="text-[var(--color-text-3)]">{label.text}</span>;
                    }
                    return (
                      <span className="block min-w-0 truncate" title={label.text}>
                        {label.text}
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
          filters={
            <Select
              allowClear
              showSearch
              placeholder="按策略模板筛选对象"
              optionFilterProp="label"
              className="w-56"
              value={memberTemplateFilter || undefined}
              options={memberTemplateFilterOptions(memberGroup?.rules || [])}
              onChange={(value) => {
                setMemberTemplateFilter(value || null);
                setMemberPagination((prev) => ({ ...prev, current: 1 }));
              }}
            />
          }
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
            { title: t('common.name'), dataIndex: 'name', key: 'name', width: 180 },
            {
              title: '生效模板',
              dataIndex: 'templates',
              key: 'templates',
              render: (_, record) => {
                const plugins = record.plugins || [];
                const templates = record.templates || [];
                if (!plugins.length) {
                  return <span className="text-[var(--color-text-3)]">未匹配</span>;
                }
                return (
                  <div className="flex flex-wrap gap-1">
                    {plugins.map((plugin) => {
                      const names = templates.filter((item) => item.plugin_name === plugin.name);
                      const tag = renderPluginTag(plugin.name);
                      if (!names.length) return <span key={plugin.id}>{tag}</span>;
                      return (
                        <Popover
                          key={plugin.id}
                          trigger="hover"
                          placement="bottomLeft"
                          styles={{ body: { padding: 0, borderRadius: 8 } }}
                          content={
                            <div className="max-h-60 w-56 overflow-auto py-1">
                              {names.map((item: PolicyGroupMemberTemplate) => (
                                <div key={item.rule_id} className="px-3 py-1 text-xs text-[var(--color-text-1)]">
                                  {item.name}
                                </div>
                              ))}
                            </div>
                          }
                        >
                          <span className="inline-flex cursor-default">{tag}</span>
                        </Popover>
                      );
                    })}
                  </div>
                );
              },
            },
            {
              title: t('common.action'),
              dataIndex: 'action',
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
        width={780}
        closable={false}
        onClose={() => {
          setRuleGroup(null);
          setRuleKeyword('');
          setRuleNoData(null);
          setRulePluginFilter('all');
          setRulePagination((prev) => ({ ...prev, current: 1 }));
        }}
      >
        <Alert
          type="info"
          showIcon
          className="mb-4"
          message="监控模板与接入方式生效说明"
          description="策略组打包了多种采集模板的规则。主机实际接入时，仅会匹配其对应接入方式生效（如远程接入的主机仅生效 Host Remote 规则，其余规则因无该时序数据源自动保持静默，不会造成误报）。"
        />

        {availablePlugins.length > 1 && (
          <div className="mb-3 flex flex-wrap items-center gap-1.5 text-[12px]">
            <span className="text-[var(--color-text-3)] mr-1">接入模板:</span>
            <Tag.CheckableTag
              checked={rulePluginFilter === 'all'}
              onChange={() => {
                setRulePluginFilter('all');
                setRulePagination((prev) => ({ ...prev, current: 1 }));
              }}
            >
              全部 ({ruleRows.length})
            </Tag.CheckableTag>
            {availablePlugins.map(({ name, count }) => (
              <Tag.CheckableTag
                key={name}
                checked={rulePluginFilter === name}
                onChange={() => {
                  setRulePluginFilter(name);
                  setRulePagination((prev) => ({ ...prev, current: 1 }));
                }}
              >
                {name} ({count})
              </Tag.CheckableTag>
            ))}
          </div>
        )}

        <SearchActionBar
          searchProps={{
            placeholder: '搜索名称或模板',
            value: ruleKeyword,
            onChange: (event) => {
              setRuleKeyword(event.target.value);
              setRulePagination((prev) => ({ ...prev, current: 1 }));
            },
          }}
          actions={
            ruleGroup ? (
              <Permission requiredPermissions={['Edit']}>
                <Button onClick={() => void openAdjustRules(ruleGroup)}>调整策略</Button>
              </Permission>
            ) : null
          }
        />
        <CustomTable
          rowKey="id"
          dataSource={visibleRules}
          pagination={{ ...rulePagination, total: filteredRules.length }}
          scroll={{ y: 'auto' }}
          onChange={(next, filters, _sorter, extra) => {
            if (extra?.action === 'filter') {
              const selected = filters?.no_data_enabled;
              const value = Array.isArray(selected) && selected.length ? String(selected[0]) : '';
              setRuleNoData(value === 'on' || value === 'off' ? value : null);
              setRulePagination((prev) => ({
                ...prev,
                current: 1,
                pageSize: next.pageSize || prev.pageSize,
              }));
              return;
            }
            setRulePagination((prev) => ({
              ...prev,
              current: next.pageSize !== prev.pageSize ? 1 : next.current || 1,
              pageSize: next.pageSize || prev.pageSize,
            }));
          }}
          columns={drawerRuleColumns}
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
            <Button
              type="primary"
              loading={detectionSaving || noticeSaving}
              disabled={
                noticeLoading ||
                (noticeEnabled && noticeTypeIds.length === 0) ||
                (noticeUsersRequired && noticeUserIds.length === 0)
              }
              onClick={saveConfig}
            >
              确认
            </Button>
            <Button disabled={detectionSaving || noticeSaving} onClick={closeConfig}>
              取消
            </Button>
          </div>
        }
      >
        {(() => {
          const notes = policyGroupDetectionNotes({
            scheduleUniform: configGroup?.schedule_uniform,
            noDataUniform: configGroup?.no_data_uniform,
          });
          const scheduleNote = notes.find((note) => note.includes('检测频率'));

          return (
            <div className="space-y-6">
              {/* 第一部分：检测与评估周期 */}
              <div className="border-b border-[var(--color-border-1)] pb-5">
                <div className="mb-2 text-[13px] font-semibold text-[var(--color-text-1)]">
                  评估周期 (Evaluation Interval)
                </div>
                {scheduleNote ? <div className={`mb-2 ${CONFIG_HINT_CLASS}`}>{scheduleNote}</div> : null}
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
                <div className={`mt-2 ${CONFIG_HINT_CLASS}`}>
                  系统执行本策略组内各规则扫描检测的时间间隔。各指标的采样汇聚仍遵循单条规则设定。
                </div>
              </div>

              {/* 第二部分：告警通知与分派 */}
              <div>
                <div className="mb-3 text-[13px] font-semibold text-[var(--color-text-1)]">
                  告警通知与分派 (Routing & Notification)
                </div>
                <Spin spinning={noticeLoading}>
                  {configGroup?.notice_uniform === false ? (
                    <div className={`mb-3 ${CONFIG_HINT_CLASS}`}>组内规则的通知渠道不一致，保存后将统一生效。</div>
                  ) : null}
                  {configGroup?.handlers_uniform === false ? (
                    <div className={`mb-3 ${CONFIG_HINT_CLASS}`}>组内规则的责任人不一致，保存后将统一生效。</div>
                  ) : null}
                  <div className="mb-4">
                    <div className="mb-1 font-medium text-[var(--color-text-2)]">告警责任人</div>
                    <Select
                      mode="multiple"
                      className="w-full max-w-[420px]"
                      showSearch
                      allowClear
                      placeholder="请选择告警责任人"
                      optionFilterProp="label"
                      value={handlerIds}
                      options={noticeUserOptions.map((item) => ({
                        value: String(item.id),
                        label: formatUserName(item),
                      }))}
                      onChange={setHandlerIds}
                    />
                    <div className={`mt-1.5 ${CONFIG_HINT_CLASS}`}>
                      产生新告警事件时默认指派给所选责任人，支持多人协同处理。
                    </div>
                  </div>

                  <div className="mb-4">
                    <div className="mb-1 font-medium text-[var(--color-text-2)]">通知推送</div>
                    <Switch checked={noticeEnabled} onChange={setNoticeEnabled} />
                    <div className={`mt-1.5 ${CONFIG_HINT_CLASS}`}>
                      开启后，本策略组触发的告警将通过选定的渠道及时发送通知。
                    </div>
                  </div>

                  {noticeEnabled ? (
                    <>
                      <div className="mb-4">
                        <div className="mb-1 font-medium text-[var(--color-text-2)]">通知方式</div>
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
                          <span className="text-[var(--color-text-3)]">暂无可用通知渠道</span>
                        )}
                      </div>
                      {noticeUsersRequired ? (
                        <div className="mb-3">
                          <div className="mb-1 font-medium text-[var(--color-text-2)]">通知接收人</div>
                          <Select
                            mode="multiple"
                            className="w-full max-w-[420px]"
                            showSearch
                            placeholder="请选择通知接收人"
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
              </div>
            </div>
          );
        })()}
      </Drawer>
      <Drawer
        title={adjustingGroup ? `调整 ${adjustingGroup.name} 的策略` : '新建策略组'}
        open={createOpen}
        width={760}
        closable={false}
        onClose={() => {
          if (createSaving) return;
          setCreateOpen(false);
          setAdjustingGroup(null);
        }}
        footer={
          <div className="flex justify-end gap-2">
            <Button
              type="primary"
              loading={createSaving}
              disabled={!adjustingGroup && (!createName.trim() || selectedTemplateIds.length === 0)}
              onClick={() => void submitCreate()}
            >
              {adjustingGroup ? '保存' : '确认'}
            </Button>
            <Button
              disabled={createSaving}
              onClick={() => {
                setCreateOpen(false);
                setAdjustingGroup(null);
              }}
            >
              取消
            </Button>
          </div>
        }
      >
        <div className={`mb-3 ${CONFIG_HINT_CLASS}`}>
          选项来自策略模板页，按当前监控对象列出。可先去模板页新增或修改模板，再回到这里勾选。{' '}
          <Link
            href={`/monitor/event/template?${MODULE_OBJECT_QUERY_PARAM}=${String(objectId || '')}`}
            className="text-[var(--color-primary)]"
          >
            去策略模板
          </Link>
        </div>
        {adjustingGroup ? (
          <div className={`mb-3 ${CONFIG_HINT_CLASS}`}>
            已勾选的是组内当前策略。取消勾选会从本策略组移除，不会删除模板。已接入对应插件的实例才会写入覆盖并开始扫描。
          </div>
        ) : (
          <div className="mb-3">
            <div className="mb-1">名称</div>
            <Input maxLength={100} value={createName} onChange={(event) => setCreateName(event.target.value)} />
          </div>
        )}
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
