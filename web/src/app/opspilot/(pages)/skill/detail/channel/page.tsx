'use client';

import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import {
  Button,
  Empty,
  Form,
  Input,
  Modal,
  Select,
  Space,
  Spin,
  Switch,
  Table,
  Tag,
  Typography,
  message,
} from 'antd';
import { useSearchParams } from 'next/navigation';
import { useTranslation } from '@/utils/i18n';
import { useSkillApi } from '@/app/opspilot/api/skill';
import PermissionWrapper from '@/components/permission';

interface SkillChannelItem {
  id: number;
  name: string;
  channel_type: string;
  enabled: boolean;
  channel_config?: Record<string, any>;
  callback_path?: string;
  usage_team?: number[];
}

const WEB_CHAT_PATH = '/opspilot/skill/chat';

const CHANNEL_OPTIONS = [
  { value: 'platform' },
  { value: 'web_chat' },
  { value: 'embedded_chat' },
  { value: 'enterprise_wechat' },
  { value: 'enterprise_wechat_aibot' },
  { value: 'dingtalk' },
  { value: 'wechat_official' },
];

const CHANNEL_TAG_COLOR: Record<string, string> = {
  platform: 'cyan',
  web_chat: 'blue',
  embedded_chat: 'purple',
  enterprise_wechat: 'green',
  enterprise_wechat_aibot: 'green',
  dingtalk: 'orange',
  wechat_official: 'lime',
};

const CONFIG_FIELDS: Record<string, string[]> = {
  enterprise_wechat: ['token', 'secret', 'aes_key', 'corp_id', 'agent_id'],
  enterprise_wechat_aibot: ['token', 'encodingAESKey', 'aibotid'],
  dingtalk: ['client_id', 'client_secret'],
  wechat_official: ['token', 'secret', 'aes_key', 'app_id'],
  platform: [],
  web_chat: ['appName', 'appDescription'],
  embedded_chat: [],
};

const channelTypeLabel = (t: (key: string, fallback?: string) => string, channelType: string) =>
  t(`skill.channel.types.${channelType}`, channelType);

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

  const [loading, setLoading] = useState(false);
  const [channels, setChannels] = useState<SkillChannelItem[]>([]);
  const [modalOpen, setModalOpen] = useState(false);
  const [editing, setEditing] = useState<SkillChannelItem | null>(null);
  const [saving, setSaving] = useState(false);
  const [nameQuery, setNameQuery] = useState('');
  const [typeFilter, setTypeFilter] = useState<string>();
  const [form] = Form.useForm();
  const channelType = Form.useWatch('channel_type', form);
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

  const load = useCallback(async () => {
    if (!skillId) return;
    setLoading(true);
    try {
      const data = await apiRef.current.fetchSkillChannels(skillId);
      setChannels(Array.isArray(data) ? data : []);
    } catch (e: any) {
      message.error(e?.message || apiRef.current.t('skill.channel.loadFailed'));
    } finally {
      setLoading(false);
    }
  }, [skillId]);

  useEffect(() => {
    void load();
  }, [load]);

  const configFields = useMemo(() => CONFIG_FIELDS[channelType] || [], [channelType]);

  const enabledCount = useMemo(() => channels.filter((c) => c.enabled).length, [channels]);
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
    setEditing(null);
    form.resetFields();
    form.setFieldsValue({ channel_type: 'platform', enabled: false });
    setModalOpen(true);
  };

  const openEdit = (item: SkillChannelItem) => {
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
            token: values.token,
            encodingAESKey: values.encodingAESKey,
            aibotid: values.aibotid || '',
          },
        };
      }
      if (editing) {
        await updateSkillChannel(editing.id, {
          name: values.name,
          channel_config,
        });
        if (typeof values.enabled === 'boolean' && values.enabled !== editing.enabled) {
          await setSkillChannelEnabled(editing.id, values.enabled);
        }
      } else {
        const created = await createSkillChannel({
          skill: Number(skillId),
          channel_type: values.channel_type,
          name: values.name || values.channel_type,
          channel_config,
          enabled: !!values.enabled,
        });
        if (values.enabled && created?.id) {
          await setSkillChannelEnabled(created.id, true);
        }
      }
      message.success(t('common.saveSuccess') || '保存成功');
      setModalOpen(false);
      await load();
    } catch (e: any) {
      if (e?.errorFields) return;
      message.error(e?.message || t('skill.channel.saveFailed'));
    } finally {
      setSaving(false);
    }
  };

  const onToggle = async (item: SkillChannelItem, enabled: boolean) => {
    try {
      await setSkillChannelEnabled(item.id, enabled);
      await load();
    } catch (e: any) {
      message.error(e?.message || t('skill.channel.toggleFailed'));
    }
  };

  const onDelete = async (item: SkillChannelItem) => {
    Modal.confirm({
      title: t('common.delete') || '删除',
      content: t('skill.channel.deleteConfirm', '确认删除渠道「{name}」？', {
        name: item.name || channelTypeLabel(t, item.channel_type),
      }),
      onOk: async () => {
        await deleteSkillChannel(item.id);
        await load();
      },
    });
  };

  const openWebChat = () => {
    window.open(WEB_CHAT_PATH, '_blank', 'noopener,noreferrer');
  };

  const columns = useMemo(
    () => [
      {
        title: t('skill.channel.name'),
        dataIndex: 'name',
        key: 'name',
        ellipsis: true,
        render: (name: string, item: SkillChannelItem) =>
          name || channelTypeLabel(t, item.channel_type),
      },
      {
        title: t('skill.channel.type'),
        dataIndex: 'channel_type',
        key: 'channel_type',
        width: 140,
        render: (channelType: string) => (
          <Tag color={CHANNEL_TAG_COLOR[channelType] || 'default'} className="!m-0">
            {channelTypeLabel(t, channelType)}
          </Tag>
        ),
      },
      {
        title: t('skill.channel.status', '状态'),
        dataIndex: 'enabled',
        key: 'enabled',
        width: 88,
        render: (_: boolean, item: SkillChannelItem) => (
          <Switch size="small" checked={item.enabled} onChange={(v) => onToggle(item, v)} />
        ),
      },
      {
        title: t('common.action') || '操作',
        key: 'action',
        width: 220,
        align: 'right' as const,
        render: (_: unknown, item: SkillChannelItem) => (
          <Space size="small">
            {item.channel_type === 'web_chat' ? (
              <Button size="small" type="primary" onClick={openWebChat}>
                {t('skill.channel.openChat', '对话')}
              </Button>
            ) : null}
            <Button size="small" onClick={() => openEdit(item)}>
              {t('common.setting') || '设置'}
            </Button>
            <Button size="small" danger onClick={() => onDelete(item)}>
              {t('common.delete') || '删除'}
            </Button>
          </Space>
        ),
      },
    ],
    [t]
  );

  return (
    <div className="flex h-full flex-col gap-4 p-4">
      <div className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
        <div className="min-w-0">
          <Typography.Title level={5} className="!mb-1">
            {t('skill.channelPublish')}
          </Typography.Title>
          <Typography.Paragraph className="!mb-0 text-xs text-[var(--color-text-3)]">
            {t(
              'skill.channel.pageDesc',
              '为当前智能体开通独立入口。配置活引用技能参数；同类型可挂多条；启停互不影响。'
            )}
          </Typography.Paragraph>
        </div>
        <PermissionWrapper requiredPermissions={['Edit']}>
          <Button type="primary" onClick={openCreate}>
            {t('skill.channel.add', '添加渠道')}
          </Button>
        </PermissionWrapper>
      </div>

      <div className="grid grid-cols-1 gap-3 sm:grid-cols-3">
        <div className="rounded-md border border-[var(--color-border-1)] bg-[var(--color-bg)] px-4 py-3">
          <div className="text-xs text-[var(--color-text-3)]">{t('skill.channel.statTotal', '渠道总数')}</div>
          <div className="mt-1 text-2xl font-semibold text-[var(--color-text-1)]">{channels.length}</div>
        </div>
        <div className="rounded-md border border-[var(--color-border-1)] bg-[var(--color-bg)] px-4 py-3">
          <div className="text-xs text-[var(--color-text-3)]">{t('skill.channel.statEnabled', '已启用')}</div>
          <div className="mt-1 text-2xl font-semibold text-[var(--color-primary)]">{enabledCount}</div>
        </div>
        <div className="rounded-md border border-[var(--color-border-1)] bg-[var(--color-bg)] px-4 py-3">
          <div className="text-xs text-[var(--color-text-3)]">{t('skill.channel.statDisabled', '未启用')}</div>
          <div className="mt-1 text-2xl font-semibold text-[var(--color-text-2)]">
            {channels.length - enabledCount}
          </div>
        </div>
      </div>

      <Spin spinning={loading}>
        {channels.length === 0 && !loading ? (
          <div className="flex min-h-[280px] items-center justify-center rounded-md border border-dashed border-[var(--color-border-2)] bg-[var(--color-fill-1)]">
            <Empty
              description={t('skill.channel.empty', '尚未发布任何渠道')}
              image={Empty.PRESENTED_IMAGE_SIMPLE}
            >
              <PermissionWrapper requiredPermissions={['Edit']}>
                <Button type="primary" onClick={openCreate}>
                  {t('skill.channel.add', '添加渠道')}
                </Button>
              </PermissionWrapper>
            </Empty>
          </div>
        ) : (
          <div className="flex flex-col gap-3 rounded-md border border-[var(--color-border-1)] bg-[var(--color-bg)] p-4">
            <div className="flex flex-col gap-2 sm:flex-row">
              <Input
                allowClear
                value={nameQuery}
                onChange={(e) => setNameQuery(e.target.value)}
                placeholder={t('skill.channel.filterNamePlaceholder', '按名称筛选')}
                className="sm:max-w-xs"
              />
              <Select
                allowClear
                value={typeFilter}
                onChange={(value) => setTypeFilter(value)}
                placeholder={t('skill.channel.filterTypeAll', '全部类型')}
                className="sm:w-48"
                options={CHANNEL_OPTIONS.map((o) => ({
                  value: o.value,
                  label: channelTypeLabel(t, o.value),
                }))}
              />
            </div>
            <Table
              rowKey="id"
              size="middle"
              pagination={false}
              columns={columns}
              dataSource={filteredChannels}
              locale={{
                emptyText: t('skill.channel.filterEmpty', '没有匹配的渠道'),
              }}
            />
          </div>
        )}
      </Spin>

      <Modal
        title={editing ? t('common.edit') || '编辑' : t('skill.channel.add', '添加渠道')}
        open={modalOpen}
        onCancel={() => setModalOpen(false)}
        onOk={onSave}
        confirmLoading={saving}
        destroyOnClose
      >
        <Form form={form} layout="vertical">
          <Form.Item name="channel_type" label={t('skill.channel.type')} rules={[{ required: true }]}>
            <Select
              disabled={!!editing}
              options={CHANNEL_OPTIONS.map((o) => ({
                value: o.value,
                label: channelTypeLabel(t, o.value),
              }))}
            />
          </Form.Item>
          <Form.Item name="name" label={t('skill.channel.name')}>
            <Input />
          </Form.Item>
          <Form.Item name="enabled" label={t('skill.channel.enabled')} valuePropName="checked">
            <Switch />
          </Form.Item>
          {configFields.map((field) => (
            <Form.Item key={field} name={field} label={field}>
              <Input.Password
                visibilityToggle={
                  field.toLowerCase().includes('secret') ||
                  field.toLowerCase().includes('token') ||
                  field.toLowerCase().includes('aes')
                }
              />
            </Form.Item>
          ))}
        </Form>
      </Modal>
    </div>
  );
};

export default SkillChannelPage;
