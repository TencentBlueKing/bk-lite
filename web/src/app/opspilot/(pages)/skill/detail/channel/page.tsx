'use client';

import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import {
  Button,
  Form,
  Input,
  Popconfirm,
  Select,
  Skeleton,
  Space,
  Switch,
  Table,
  Tag,
  Tooltip,
  message,
} from 'antd';
import {
  PlusOutlined,
  ReloadOutlined,
  CheckCircleOutlined,
  StopOutlined,
  DeploymentUnitOutlined,
  InfoCircleOutlined,
  CopyOutlined,
} from '@ant-design/icons';
import Link from 'next/link';
import { useSearchParams } from 'next/navigation';
import { useTranslation } from '@/utils/i18n';
import { useSkillApi } from '@/app/opspilot/api/skill';
import PermissionWrapper from '@/components/permission';
import { notifyWebchatAppsChanged } from '@/app/(core)/components/global-webchat/apps-changed';
import SummaryMetricCard from '@/components/summary-metric-card';
import ToolbarSplitShell from '@/components/toolbar-split-shell';
import CompactEmptyState from '@/components/compact-empty-state';
import OperateModal from '@/components/operate-modal';
import Icon from '@/components/icon';
import OpsPilotChannelPageSkeleton from '@/app/opspilot/components/opspilot-channel-page-skeleton';
import { rememberWebChatEntry } from '@/app/opspilot/(pages)/skill/chat/entry';

interface SkillChannelItem {
  id: number;
  public_id?: string;
  name: string;
  channel_type: string;
  enabled: boolean;
  channel_config?: Record<string, any>;
  callback_path?: string;
  usage_team?: number[];
}

type TableItem = SkillChannelItem & { isSkeleton?: boolean };

const SKELETON_ROWS: TableItem[] = [
  { id: -1, name: '', channel_type: '', enabled: false, isSkeleton: true },
  { id: -2, name: '', channel_type: '', enabled: false, isSkeleton: true },
  { id: -3, name: '', channel_type: '', enabled: false, isSkeleton: true },
  { id: -4, name: '', channel_type: '', enabled: false, isSkeleton: true },
  { id: -5, name: '', channel_type: '', enabled: false, isSkeleton: true },
];

const WEB_CHAT_PATH = '/opspilot/skill/chat';
const SKILL_API_DOCS_PATH = '/opspilot/skill/detail/api';
const IM_CALLBACK_TYPES = new Set([
  'enterprise_wechat',
  'enterprise_wechat_aibot',
  'dingtalk',
  'feishu',
  'wechat_official',
]);

const needsPublicLink = (channelType?: string) =>
  !!channelType && (IM_CALLBACK_TYPES.has(channelType) || channelType === 'embedded_chat');

const generatePublicId = () => {
  if (typeof crypto !== 'undefined' && typeof crypto.randomUUID === 'function') {
    return crypto.randomUUID();
  }
  return 'xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx'.replace(/[xy]/g, (c) => {
    const r = (Math.random() * 16) | 0;
    const v = c === 'x' ? r : (r & 0x3) | 0x8;
    return v.toString(16);
  });
};

const consoleOrigin = () => (typeof window !== 'undefined' ? window.location.origin : '');

const skillEmbeddedChatUrl = (skillId: string, channelRef: number | string) =>
  `${consoleOrigin()}/api/v1/opspilot/skill_channel/embedded/${skillId}/${channelRef}/`;

const skillChannelCallbackPath = (channelRef: number | string, channelType: string) =>
  `/api/v1/opspilot/skill_channel/${channelRef}/${channelType}/`;

const skillChannelCallbackUrl = (
  channel: Pick<SkillChannelItem, 'id' | 'channel_type' | 'callback_path' | 'public_id'>
) => {
  const ref = channel.public_id || channel.id;
  const path = channel.callback_path || skillChannelCallbackPath(ref, channel.channel_type);
  return path.startsWith('http') ? path : `${consoleOrigin()}${path}`;
};

const toChannelRecord = (raw: unknown, fallbackType: string): SkillChannelItem | null => {
  const envelope = raw && typeof raw === 'object' ? (raw as Record<string, unknown>) : null;
  const row = envelope && typeof envelope.id === 'number'
    ? envelope
    : envelope && envelope.data && typeof envelope.data === 'object'
      ? (envelope.data as Record<string, unknown>)
      : null;
  if (typeof row.id !== 'number') {
    return null;
  }
  const id = row.id;
  const publicId = row.public_id;
  return {
    id,
    public_id: typeof publicId === 'string' ? publicId : '',
    name: typeof row.name === 'string' ? row.name : '',
    channel_type: typeof row.channel_type === 'string' ? row.channel_type : fallbackType,
    enabled: Boolean(row.enabled),
    channel_config:
      row.channel_config && typeof row.channel_config === 'object'
        ? (row.channel_config as Record<string, any>)
        : undefined,
    callback_path: typeof row.callback_path === 'string' ? row.callback_path : undefined,
  };
};

const skillApiDocsHref = (skillId?: string | null) => {
  if (!skillId) {
    return SKILL_API_DOCS_PATH;
  }
  return `${SKILL_API_DOCS_PATH}?id=${encodeURIComponent(skillId)}`;
};

const copyText = async (text: string) => {
  try {
    await navigator.clipboard.writeText(text);
  } catch {
    const textArea = document.createElement('textarea');
    textArea.value = text;
    document.body.appendChild(textArea);
    textArea.select();
    document.execCommand('copy');
    document.body.removeChild(textArea);
  }
};

const CHANNEL_OPTIONS = [
  { value: 'platform' },
  { value: 'web_chat' },
  { value: 'embedded_chat' },
  { value: 'enterprise_wechat' },
  { value: 'enterprise_wechat_aibot' },
  { value: 'dingtalk' },
  { value: 'feishu' },
  { value: 'wechat_official' },
];

const CHANNEL_META: Record<string, { icon: string; color: string }> = {
  platform: { icon: 'jiqiren3', color: 'cyan' },
  web_chat: { icon: 'WebSphereMQ', color: 'blue' },
  embedded_chat: { icon: 'wendaduihua', color: 'purple' },
  enterprise_wechat: { icon: 'qiwei2', color: 'green' },
  enterprise_wechat_aibot: { icon: 'qiwei2', color: 'green' },
  dingtalk: { icon: 'dingding', color: 'orange' },
  feishu: { icon: 'feishu', color: 'blue' },
  wechat_official: { icon: 'weixingongzhonghao', color: 'lime' },
};

const CONFIG_FIELDS: Record<string, string[]> = {
  enterprise_wechat: ['token', 'secret', 'aes_key', 'corp_id', 'agent_id'],
  enterprise_wechat_aibot: ['token', 'encodingAESKey'],
  dingtalk: ['client_id', 'client_secret'],
  feishu: ['app_id', 'app_secret', 'encrypt_key', 'verification_token'],
  wechat_official: ['token', 'secret', 'aes_key', 'app_id'],
  platform: [],
  web_chat: [],
  embedded_chat: [],
};

const channelTypeLabel = (t: (key: string, fallback?: string) => string, channelType: string) =>
  t(`skill.channel.types.${channelType}`, channelType);

const channelFieldLabel = (t: (key: string, fallback?: string) => string, field: string) =>
  t(`skill.channel.fields.${field}`, field);

const isSecretConfigField = (field: string) => {
  const key = field.toLowerCase();
  return key.includes('secret') || key.includes('token') || key.includes('aes') || key.includes('key');
};

const ChannelTypeIcon: React.FC<{ channelType: string; className?: string }> = ({
  channelType,
  className = '',
}) => {
  const meta = CHANNEL_META[channelType] || { icon: 'gongju', color: 'default' };
  return <Icon type={meta.icon} className={`text-base shrink-0 ${className}`} />;
};

const SkillChannelPage: React.FC = () => {
  const { t } = useTranslation();
  const searchParams = useSearchParams();
  const skillId = searchParams?.get('id');
  const {
    fetchSkillChannels,
    createSkillChannel,
    updateSkillChannel,
    setSkillChannelEnabled,
    deleteSkillChannel,
  } = useSkillApi();

  const [initialLoading, setInitialLoading] = useState(true);
  const [loading, setLoading] = useState(false);
  const [channels, setChannels] = useState<SkillChannelItem[]>([]);
  const [modalOpen, setModalOpen] = useState(false);
  const [editing, setEditing] = useState<SkillChannelItem | null>(null);
  const [saving, setSaving] = useState(false);
  const [draftPublicId, setDraftPublicId] = useState('');
  const [nameQuery, setNameQuery] = useState('');
  const [typeFilter, setTypeFilter] = useState<string>();
  const [switchLoading, setSwitchLoading] = useState<Record<number, boolean>>({});
  const [form] = Form.useForm();
  const watchedType = Form.useWatch('channel_type', form);
  const activeType = editing?.channel_type || watchedType;
  const publicRef = (editing?.public_id || draftPublicId || '').toString();
  const callbackUrl =
    activeType && IM_CALLBACK_TYPES.has(activeType) && (editing || publicRef)
      ? skillChannelCallbackUrl({
        id: editing?.id || 0,
        public_id: publicRef || undefined,
        channel_type: activeType,
        callback_path: editing?.callback_path,
      })
      : '';
  const embeddedUrl = skillId && needsPublicLink(activeType) && activeType === 'embedded_chat' && (publicRef || editing)
    ? skillEmbeddedChatUrl(skillId, publicRef || editing?.id || '')
    : '';

  const apiRef = useRef({
    fetchSkillChannels,
    createSkillChannel,
    updateSkillChannel,
    setSkillChannelEnabled,
    deleteSkillChannel,
    t,
  });
  apiRef.current = {
    fetchSkillChannels,
    createSkillChannel,
    updateSkillChannel,
    setSkillChannelEnabled,
    deleteSkillChannel,
    t,
  };

  const load = useCallback(async (isInitial = false) => {
    if (!skillId) {
      setInitialLoading(false);
      return;
    }
    if (isInitial) {
      setInitialLoading(true);
    } else {
      setLoading(true);
    }
    try {
      const data = await apiRef.current.fetchSkillChannels(skillId);
      setChannels(Array.isArray(data) ? data : []);
    } catch (e: any) {
      message.error(e?.message || apiRef.current.t('skill.channel.loadFailed'));
    } finally {
      setInitialLoading(false);
      setLoading(false);
    }
  }, [skillId]);

  useEffect(() => {
    void load(true);
  }, [load]);

  const configFields = useMemo(() => CONFIG_FIELDS[activeType] || [], [activeType]);

  const enabledCount = useMemo(() => channels.filter((c) => c.enabled).length, [channels]);
  const disabledCount = useMemo(() => channels.length - enabledCount, [channels.length, enabledCount]);

  const filteredChannels = useMemo(() => {
    const keyword = nameQuery.trim().toLowerCase();
    return channels.filter((item) => {
      const displayName = (item.name || channelTypeLabel(t, item.channel_type)).toLowerCase();
      const matchName = !keyword || displayName.includes(keyword);
      const matchType = !typeFilter || item.channel_type === typeFilter;
      return matchName && matchType;
    });
  }, [channels, nameQuery, typeFilter, t]);

  const openCreate = () => {
    setDraftPublicId('');
    setEditing(null);
    form.resetFields();
    form.setFieldsValue({ channel_type: 'platform', enabled: true });
    setModalOpen(true);
  };

  const openEdit = (item: SkillChannelItem) => {
    setDraftPublicId('');
    setEditing(item);
    const cfg = item.channel_config || {};
    const flat = { ...cfg, ...(cfg.webhook || {}) };
    form.setFieldsValue({
      channel_type: item.channel_type,
      name: item.name,
      enabled: item.enabled,
      ...Object.fromEntries((CONFIG_FIELDS[item.channel_type] || []).map((k) => [k, flat[k]])),
    });
    setModalOpen(true);
  };

  const closeModal = () => {
    setDraftPublicId('');
    setEditing(null);
    setModalOpen(false);
  };

  const onTypeChange = (value: string) => {
    if (editing) {
      return;
    }
    setDraftPublicId(needsPublicLink(value) ? generatePublicId() : '');
  };

  const onSave = async () => {
    if (!skillId) return;
    const values = await form.validateFields();
    setSaving(true);
    try {
      const fields = CONFIG_FIELDS[values.channel_type] || [];
      let channel_config: Record<string, any> = {};
      for (const key of fields) {
        if (values[key] !== undefined && values[key] !== '') {
          channel_config[key] = values[key];
        }
      }
      if (values.channel_type === 'enterprise_wechat_aibot') {
        channel_config = {
          connectionMode: 'webhook',
          webhook: {
            token: (values.token || '').trim(),
            encodingAESKey: (values.encodingAESKey || '').trim(),
          },
        };
      }
      if (editing) {
        await updateSkillChannel(editing.id, {
          name: values.name || editing.name,
          channel_config,
        });
        if (typeof values.enabled === 'boolean' && values.enabled !== editing.enabled) {
          await setSkillChannelEnabled(editing.id, values.enabled);
        }
      } else {
        const created = toChannelRecord(
          await createSkillChannel({
            skill: Number(skillId),
            channel_type: values.channel_type,
            name: values.name || values.channel_type,
            channel_config,
            enabled: !!values.enabled,
            ...(draftPublicId ? { public_id: draftPublicId } : {}),
          }),
          values.channel_type
        );
        if (values.enabled && created?.id) {
          await setSkillChannelEnabled(created.id, true);
        }
      }
      message.success(t('common.saveSuccess', '保存成功'));
      await load(false);
      notifyWebchatAppsChanged();
      closeModal();
    } catch (e: any) {
      if (e?.errorFields) return;
      const detail = e?.response?.data?.name || e?.response?.data?.message || e?.message;
      message.error(
        Array.isArray(detail) ? detail[0] : detail || t('skill.channel.saveFailed', '保存失败')
      );
    } finally {
      setSaving(false);
    }
  };

  const onToggle = async (item: SkillChannelItem, enabled: boolean) => {
    setSwitchLoading((prev) => ({ ...prev, [item.id]: true }));
    try {
      await setSkillChannelEnabled(item.id, enabled);
      await load(false);
      notifyWebchatAppsChanged();
    } catch (e: any) {
      message.error(e?.message || t('skill.channel.toggleFailed', '启停失败'));
    } finally {
      setSwitchLoading((prev) => ({ ...prev, [item.id]: false }));
    }
  };

  const onDelete = async (item: SkillChannelItem) => {
    try {
      await deleteSkillChannel(item.id);
      message.success(t('common.deleteSuccess', '删除成功'));
      await load(false);
      notifyWebchatAppsChanged();
    } catch (e: any) {
      message.error(e?.message || t('common.deleteFailed', '删除失败'));
    }
  };

  const openWebChat = (channelId: number) => {
    const token = rememberWebChatEntry(channelId);
    window.open(`${WEB_CHAT_PATH}?entry=${token}`, '_blank', 'noopener,noreferrer');
  };

  const copyEmbeddedLink = async (channelRef: number | string) => {
    if (!skillId || !channelRef) {
      return;
    }
    try {
      await copyText(skillEmbeddedChatUrl(skillId, channelRef));
      message.success(t('common.copySuccess', '复制成功'));
    } catch {
      message.error(t('common.copyFailed', '复制失败'));
    }
  };

  const copyCallbackUrl = async (url: string) => {
    if (!url) {
      return;
    }
    try {
      await copyText(url);
      message.success(t('common.copySuccess', '复制成功'));
    } catch {
      message.error(t('common.copyFailed', '复制失败'));
    }
  };

  const columns = useMemo(
    () => [
      {
        title: t('skill.channel.name', '名称'),
        dataIndex: 'name',
        key: 'name',
        render: (name: string, item: TableItem) => {
          if (item.isSkeleton) {
            return (
              <div className="flex items-center gap-2">
                <Skeleton.Avatar active size={20} shape="square" className="!rounded" />
                <Skeleton.Input active size="small" className="!h-4 !w-36 !min-w-0" />
              </div>
            );
          }
          const displayName = name || channelTypeLabel(t, item.channel_type);
          return (
            <div className="flex items-center gap-2">
              <ChannelTypeIcon channelType={item.channel_type} />
              <div className="min-w-0 flex-1">
                <div
                  className="truncate font-medium text-[var(--color-text-1)]"
                  title={displayName}
                >
                  {displayName}
                </div>
                {item.channel_type === 'web_chat' ? (
                  <div className="truncate text-xs text-[var(--color-text-3)]">
                    {t('skill.channel.webChatEntry', 'Web 对话入口')}
                  </div>
                ) : null}
                {item.channel_type === 'embedded_chat' ? (
                  <div className="truncate text-xs text-[var(--color-text-3)]">
                    {t('skill.channel.embeddedEntry', '嵌入式对话入口')}
                  </div>
                ) : null}
              </div>
            </div>
          );
        },
      },
      {
        title: t('skill.channel.type', '渠道类型'),
        dataIndex: 'channel_type',
        key: 'channel_type',
        width: 150,
        render: (type: string, item: TableItem) => {
          if (item.isSkeleton) {
            return <Skeleton.Input active size="small" className="!h-5 !w-16 !min-w-0 !rounded" />;
          }
          const meta = CHANNEL_META[type];
          return (
            <Tag color={meta?.color || 'default'} className="!m-0">
              {channelTypeLabel(t, type)}
            </Tag>
          );
        },
      },
      {
        title: t('skill.channel.status', '启停'),
        dataIndex: 'enabled',
        key: 'enabled',
        width: 130,
        render: (_: boolean, item: TableItem) => {
          if (item.isSkeleton) {
            return (
              <div className="flex items-center gap-2">
                <Skeleton.Input active size="small" className="!h-4 !w-7 !min-w-0 !rounded-full" />
                <Skeleton.Input active size="small" className="!h-3.5 !w-10 !min-w-0" />
              </div>
            );
          }
          return (
            <div className="flex items-center gap-2">
              <Switch
                size="small"
                checked={item.enabled}
                loading={switchLoading[item.id] || false}
                onChange={(v) => onToggle(item, v)}
              />
              <span
                className={`text-xs ${
                  item.enabled
                    ? 'text-[var(--color-text-2)]'
                    : 'text-[var(--color-text-4)]'
                }`}
              >
                {item.enabled
                  ? t('skill.channel.statusEnabled', '已启用')
                  : t('skill.channel.statusDisabled', '未启用')}
              </span>
            </div>
          );
        },
      },
      {
        title: t('common.action', '操作'),
        key: 'action',
        width: 160,
        render: (_: unknown, item: TableItem) => {
          if (item.isSkeleton) {
            return (
              <div className="flex items-center gap-3">
                <Skeleton.Input active size="small" className="!h-4 !w-8 !min-w-0" />
                <Skeleton.Input active size="small" className="!h-4 !w-8 !min-w-0" />
              </div>
            );
          }
          return (
            <Space size="small">
              {item.channel_type === 'web_chat' ? (
                <Button type="link" size="small" onClick={() => openWebChat(item.id)}>
                  {t('skill.channel.openChat', '对话')}
                </Button>
              ) : null}
              <Button type="link" size="small" onClick={() => openEdit(item)}>
                {t('common.edit', '编辑')}
              </Button>
              <Popconfirm
                title={t('common.delete', '删除')}
                description={t('skill.channel.deleteConfirm', '确认删除渠道「{name}」？', {
                  name: item.name || channelTypeLabel(t, item.channel_type),
                })}
                onConfirm={() => onDelete(item)}
                okText={t('common.confirm', '确认')}
                cancelText={t('common.cancel', '取消')}
                okButtonProps={{ danger: true }}
              >
                <Button type="link" size="small" danger>
                  {t('common.delete', '删除')}
                </Button>
              </Popconfirm>
            </Space>
          );
        },
      },
    ],
    [t, switchLoading]
  );

  const isFilterActive = !!nameQuery.trim() || !!typeFilter;

  if (initialLoading) {
    return <OpsPilotChannelPageSkeleton />;
  }

  return (
    <div className="flex h-full flex-col">
      {/* 顶部引导说明横幅 */}
      <div className="mb-4 flex items-center justify-between rounded-lg border border-[var(--color-border)] bg-[var(--color-fill-1)]/40 px-4 py-2.5">
        <div className="flex items-center gap-2 text-xs text-[var(--color-text-2)]">
          <InfoCircleOutlined className="text-sm text-[var(--color-primary)]" />
          <span>
            {t(
              'skill.channel.pageDesc',
              '为当前智能体开通独立入口，配置各引用技能参数；同类型可挂多条，启停互不影响。'
            )}
          </span>
        </div>
      </div>

      {/* 状态统计卡片 */}
      <div className="mb-4 grid grid-cols-1 gap-3 sm:grid-cols-3">
        <SummaryMetricCard
          icon={<DeploymentUnitOutlined />}
          iconBackground="var(--color-fill-1)"
          iconColor="var(--color-primary)"
          label={t('skill.channel.statTotal', '渠道总数')}
          value={channels.length}
          framed
          className="px-4 py-3"
        />
        <SummaryMetricCard
          icon={<CheckCircleOutlined />}
          iconBackground="rgba(82, 196, 26, 0.12)"
          iconColor="var(--color-success)"
          label={t('skill.channel.statEnabled', '已启用')}
          value={enabledCount}
          framed
          className="px-4 py-3"
        />
        <SummaryMetricCard
          icon={<StopOutlined />}
          iconBackground="var(--color-fill-1)"
          iconColor="var(--color-text-3)"
          label={t('skill.channel.statDisabled', '未启用')}
          value={disabledCount}
          framed
          className="px-4 py-3"
        />
      </div>

      {/* 工具栏：搜索与操作成组靠右 */}
      <ToolbarSplitShell
        leading={
          <div className="flex items-center gap-2">
            <span className="text-sm font-semibold text-[var(--color-text-1)]">
              {t('skill.channelPublish', '发布')}
            </span>
            <span className="text-xs text-[var(--color-text-3)]">
              ({filteredChannels.length})
            </span>
          </div>
        }
        trailing={
          <>
            <Select
              allowClear
              value={typeFilter}
              onChange={(value) => setTypeFilter(value)}
              placeholder={t('skill.channel.filterTypeAll', '全部类型')}
              className="w-36"
              options={CHANNEL_OPTIONS.map((o) => ({
                value: o.value,
                label: channelTypeLabel(t, o.value),
              }))}
            />
            <Input.Search
              allowClear
              value={nameQuery}
              onChange={(e) => setNameQuery(e.target.value)}
              placeholder={t('skill.channel.filterNamePlaceholder', '按名称筛选')}
              className="w-60"
            />
            <Tooltip title={t('common.refresh', '刷新')}>
              <Button icon={<ReloadOutlined />} onClick={() => void load(false)} loading={loading} />
            </Tooltip>
            <PermissionWrapper requiredPermissions={['Edit']}>
              <Button type="primary" icon={<PlusOutlined />} onClick={openCreate}>
                {t('skill.channel.add', '添加渠道')}
              </Button>
            </PermissionWrapper>
          </>
        }
      />

      {/* 表格主体 */}
      <div className="flex-grow">
        <Table
          rowKey="id"
          size="middle"
          pagination={false}
          columns={columns}
          dataSource={loading ? SKELETON_ROWS : filteredChannels}
          scroll={{ y: 'calc(100vh - 430px)' }}
          locale={{
            emptyText: loading ? null : isFilterActive ? (
              <div className="py-8">
                <CompactEmptyState
                  description={t('skill.channel.filterEmpty', '没有匹配的渠道')}
                />
                <Button
                  className="mt-2"
                  size="small"
                  onClick={() => {
                    setNameQuery('');
                    setTypeFilter(undefined);
                  }}
                >
                  {t('common.reset', '清空筛选')}
                </Button>
              </div>
            ) : (
              <div className="py-8">
                <CompactEmptyState
                  description={t('skill.channel.empty', '尚未发布任何渠道')}
                />
                <PermissionWrapper requiredPermissions={['Edit']}>
                  <Button
                    type="primary"
                    size="small"
                    icon={<PlusOutlined />}
                    className="mt-2"
                    onClick={openCreate}
                  >
                    {t('skill.channel.add', '添加渠道')}
                  </Button>
                </PermissionWrapper>
              </div>
            ),
          }}
        />
      </div>

      {/* 添加/编辑渠道弹窗 */}
      <OperateModal
        title={editing ? t('common.edit', '编辑') : t('skill.channel.add', '添加渠道')}
        subTitle={editing ? channelTypeLabel(t, editing.channel_type) : undefined}
        open={modalOpen}
        onCancel={closeModal}
        footer={[
          <Button key="cancel" onClick={closeModal}>
            {t('common.cancel', '取消')}
          </Button>,
          <Button key="submit" type="primary" loading={saving} onClick={onSave}>
            {t('common.confirm', '确定')}
          </Button>,
        ]}
        width={560}
        destroyOnClose
      >
        <Form form={form} layout="vertical" className="pt-2">
          <Form.Item
            name="channel_type"
            label={t('skill.channel.type', '渠道类型')}
            rules={[{ required: true, message: t('common.required', '此项必填') }]}
          >
            <Select
              disabled={!!editing}
              virtual={false}
              onChange={onTypeChange}
              optionRender={(option) => (
                <div className="flex items-center gap-2">
                  <ChannelTypeIcon channelType={String(option.value)} />
                  <span>{channelTypeLabel(t, String(option.value))}</span>
                </div>
              )}
              options={CHANNEL_OPTIONS.map((o) => ({
                value: o.value,
                label: channelTypeLabel(t, o.value),
              }))}
            />
          </Form.Item>
          <Form.Item name="name" label={t('skill.channel.name', '名称')}>
            <Input placeholder={t('skill.channel.namePlaceholder', '选填，便于识别不同入口')} />
          </Form.Item>
          <Form.Item
            name="enabled"
            label={t('skill.channel.enabled', '启用')}
            valuePropName="checked"
          >
            <Switch />
          </Form.Item>
          {activeType && IM_CALLBACK_TYPES.has(activeType) ? (
            <Form.Item
              label={t('skill.channel.callbackUrl', '回调地址')}
              extra={t(
                'skill.channel.callbackUrlHint',
                '复制此地址到企微 / 钉钉 / 飞书 / 公众号后台。请先点确定保存，再让对方校验该 URL。'
              )}
            >
              <Space.Compact className="w-full">
                <Input
                  readOnly
                  value={callbackUrl}
                  placeholder={t('skill.channel.callbackUrlSaveHint', '选择渠道类型后自动生成')}
                />
                <Button
                  icon={<CopyOutlined />}
                  aria-label={t('common.copy', '复制')}
                  disabled={!callbackUrl}
                  onClick={() => void copyCallbackUrl(callbackUrl)}
                />
              </Space.Compact>
            </Form.Item>
          ) : null}
          {activeType === 'embedded_chat' ? (
            <div className="mb-4 rounded-md border border-[var(--color-border)] bg-[var(--color-fill-1)] px-3 py-2.5 text-xs leading-5 text-[var(--color-text-3)]">
              <p className="mb-2">
                {t(
                  'skill.channel.embeddedApiInfo',
                  '提供可通过 WebChat 嵌入网页的对话接口。选择类型后即可复制下方调用地址，请先点确定保存再对接。'
                )}
              </p>
              {embeddedUrl ? (
                <div className="relative mb-2">
                  <Input.TextArea
                    readOnly
                    value={embeddedUrl}
                    autoSize={{ minRows: 2, maxRows: 4 }}
                    className="pr-10 font-mono text-xs"
                  />
                  <Button
                    type="text"
                    icon={<CopyOutlined />}
                    size="small"
                    className="absolute top-1 right-1"
                    aria-label={t('common.copy', '复制')}
                    onClick={() => void copyEmbeddedLink(publicRef || editing?.id || '')}
                  />
                </div>
              ) : null}
              <span>{t('skill.channel.moreDetails', '如何对接请查看')}</span>
              <Link
                href={skillApiDocsHref(skillId)}
                target="_blank"
                className="text-[var(--color-primary)] hover:underline"
              >
                {t('skill.channel.viewApiDocs', '接入文档 →')}
              </Link>
            </div>
          ) : null}
          {configFields.map((field) => (
            <React.Fragment key={field}>
              <Form.Item
                name={field}
                label={channelFieldLabel(t, field)}
              >
                {isSecretConfigField(field) ? (
                  <Input.Password visibilityToggle />
                ) : field === 'appDescription' ? (
                  <Input.TextArea rows={3} />
                ) : (
                  <Input />
                )}
              </Form.Item>
            </React.Fragment>
          ))}
        </Form>
      </OperateModal>
    </div>
  );
};

export default SkillChannelPage;
