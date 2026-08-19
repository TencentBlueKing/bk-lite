'use client';

import React, { useCallback, useEffect, useMemo, useState } from 'react';
import { Button, Form, Input, Modal, Select, Space, Spin, Switch, Typography, message } from 'antd';
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
};

const CHANNEL_OPTIONS = [
  { value: 'platform', labelKey: 'platform' },
  { value: 'web_chat', labelKey: 'web_chat' },
  { value: 'embedded_chat', labelKey: 'embedded_chat' },
  { value: 'enterprise_wechat', labelKey: 'enterprise_wechat' },
  { value: 'enterprise_wechat_aibot', labelKey: 'enterprise_wechat_aibot' },
  { value: 'dingtalk', labelKey: 'dingtalk' },
  { value: 'wechat_official', labelKey: 'wechat_official' },
];

const CONFIG_FIELDS: Record<string, string[]> = {
  enterprise_wechat: ['token', 'secret', 'aes_key', 'corp_id', 'agent_id'],
  enterprise_wechat_aibot: ['token', 'encodingAESKey', 'aibotid'],
  dingtalk: ['client_id', 'client_secret'],
  wechat_official: ['token', 'secret', 'aes_key', 'app_id'],
  platform: [],
  web_chat: ['appName', 'appDescription'],
  embedded_chat: [],
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

  const [loading, setLoading] = useState(false);
  const [channels, setChannels] = useState<SkillChannelItem[]>([]);
  const [modalOpen, setModalOpen] = useState(false);
  const [editing, setEditing] = useState<SkillChannelItem | null>(null);
  const [saving, setSaving] = useState(false);
  const [form] = Form.useForm();
  const channelType = Form.useWatch('channel_type', form);

  const load = useCallback(async () => {
    if (!skillId) return;
    setLoading(true);
    try {
      const data = await fetchSkillChannels(skillId);
      setChannels(Array.isArray(data) ? data : []);
    } catch (e: any) {
      message.error(e?.message || '加载渠道失败');
    } finally {
      setLoading(false);
    }
  }, [skillId]);

  useEffect(() => {
    void load();
  }, [load]);

  const configFields = useMemo(() => CONFIG_FIELDS[channelType] || [], [channelType]);

  const openCreate = () => {
    setEditing(null);
    form.resetFields();
    form.setFieldsValue({ channel_type: 'platform', enabled: false });
    setModalOpen(true);
  };

  const openEdit = (item: SkillChannelItem) => {
    setEditing(item);
    const cfg = item.channel_config || {};
    // aibot 可能嵌套 webhook
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
      message.error(e?.message || '保存失败');
    } finally {
      setSaving(false);
    }
  };

  const onToggle = async (item: SkillChannelItem, enabled: boolean) => {
    try {
      await setSkillChannelEnabled(item.id, enabled);
      await load();
    } catch (e: any) {
      message.error(e?.message || '启停失败');
    }
  };

  const onDelete = async (item: SkillChannelItem) => {
    Modal.confirm({
      title: t('common.delete') || '删除',
      content: `确认删除渠道「${item.name || item.channel_type}」？`,
      onOk: async () => {
        await deleteSkillChannel(item.id);
        await load();
      },
    });
  };

  return (
    <div className="p-4">
      <div className="mb-4 flex items-center justify-between">
        <Typography.Title level={5} className="!mb-0">
          {t('skill.channelPublish') || '渠道发布'}
        </Typography.Title>
        <PermissionWrapper requiredPermissions={['Edit']}>
          <Button type="primary" onClick={openCreate}>
            {t('common.add') || '新增'}
          </Button>
        </PermissionWrapper>
      </div>
      <Spin spinning={loading}>
        <div className="grid grid-cols-1 gap-4 md:grid-cols-2 xl:grid-cols-3">
          {channels.map((item) => (
            <div key={item.id} className="rounded border border-[var(--color-border-1)] p-4">
              <div className="mb-2 flex items-center justify-between">
                <div className="font-medium">{item.name || item.channel_type}</div>
                <Switch checked={item.enabled} onChange={(v) => onToggle(item, v)} />
              </div>
              <div className="mb-2 text-xs text-[var(--color-text-3)]">{item.channel_type}</div>
              {item.callback_path ? (
                <Typography.Paragraph copyable className="!mb-2 text-xs" ellipsis>
                  {item.callback_path}
                </Typography.Paragraph>
              ) : null}
              {item.channel_type === 'web_chat' ? (
                <Typography.Paragraph className="!mb-2 text-xs text-[var(--color-text-3)]">
                  Web 对话入口：
                  <Typography.Link href="/opspilot/skill/chat" target="_blank">
                    /opspilot/skill/chat
                  </Typography.Link>
                </Typography.Paragraph>
              ) : null}
              {item.channel_type === 'embedded_chat' ? (
                <Typography.Paragraph className="!mb-2 text-xs text-[var(--color-text-3)]">
                  嵌入式请求需携带 Api-Authorization（系统管理 UserAPISecret），路径含 skill_id 与 channel_id。
                </Typography.Paragraph>
              ) : null}
              <Space>
                <Button size="small" onClick={() => openEdit(item)}>
                  {t('common.setting') || '设置'}
                </Button>
                <Button size="small" danger onClick={() => onDelete(item)}>
                  {t('common.delete') || '删除'}
                </Button>
              </Space>
            </div>
          ))}
        </div>
      </Spin>

      <Modal
        title={editing ? t('common.edit') || '编辑' : t('common.add') || '新增'}
        open={modalOpen}
        onCancel={() => setModalOpen(false)}
        onOk={onSave}
        confirmLoading={saving}
        destroyOnClose
      >
        <Form form={form} layout="vertical">
          <Form.Item name="channel_type" label="渠道类型" rules={[{ required: true }]}>
            <Select
              disabled={!!editing}
              options={CHANNEL_OPTIONS.map((o) => ({ value: o.value, label: o.value }))}
            />
          </Form.Item>
          <Form.Item name="name" label="名称">
            <Input />
          </Form.Item>
          <Form.Item name="enabled" label="启用" valuePropName="checked">
            <Switch />
          </Form.Item>
          {configFields.map((field) => (
            <Form.Item key={field} name={field} label={field}>
              <Input.Password visibilityToggle={field.toLowerCase().includes('secret') || field.toLowerCase().includes('token') || field.toLowerCase().includes('aes')} />
            </Form.Item>
          ))}
        </Form>
      </Modal>
    </div>
  );
};

export default SkillChannelPage;
