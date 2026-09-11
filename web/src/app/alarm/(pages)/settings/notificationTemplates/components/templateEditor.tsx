'use client';

import React, { useEffect, useMemo, useRef, useState } from 'react';
import axios from 'axios';
import dynamic from 'next/dynamic';
import { useScreenAwareRouter } from '@/console-layout';
import DOMPurify from 'dompurify';
import MarkdownIt from 'markdown-it';
import { Alert, Button, Card, Form, Input, Modal, Select, Space, Spin, Tabs, Tag, Typography, message } from 'antd';
import { ArrowLeftOutlined, EyeOutlined, SaveOutlined } from '@ant-design/icons';
import { useSettingApi } from '@/app/alarm/api/settings';
import { useAlarmApi } from '@/app/alarm/api/alarms';
import { AlarmTableDataItem } from '@/app/alarm/types/alarms';
import { useCommon } from '@/app/alarm/context/common';
import { useUserInfoContext } from '@/context/userInfo';
import {
  NotificationTemplateContent,
  NotificationTemplateItem,
  NotificationTemplatePayload,
  NotificationTemplatePreview,
} from '@/app/alarm/types/settings';
import { useTranslation } from '@/utils/i18n';
import { HandledRequestError } from '@/utils/request';
import {
  getNotificationTemplateChannel,
  NOTIFICATION_TEMPLATE_CHANNELS,
} from '@/app/alarm/utils/notificationTemplateChannels';
import {
  DEFAULT_ALERT_OPERATION_TEMPLATE_CONTENTS,
  DEFAULT_NOTIFICATION_TEMPLATE_CONTENTS as DEFAULT_CONTENTS,
  formatLegacyAlertOperationContent,
} from '@/app/alarm/utils/defaultNotificationTemplateContents';

const AceEditor = dynamic(
  async () => {
    const ace = await import('react-ace');
    await import('ace-builds/src-noconflict/mode-html');
    await import('ace-builds/src-noconflict/mode-markdown');
    await import('ace-builds/src-noconflict/mode-text');
    await import('ace-builds/src-noconflict/theme-github');
    return ace;
  },
  { ssr: false },
);
const markdown = new MarkdownIt({ html: false, linkify: false, breaks: true });

interface TemplateEditorProps {
  templateId?: string;
}

interface TemplateApiError {
  detail?: string;
  revision?: string;
  channel_id?: string;
  alert_id?: string;
  channel_type?: string;
  template_id?: string;
  receivers?: string;
  contents?: Array<{ detail?: string }>;
}

const getApiError = (error: unknown) => {
  if (axios.isAxiosError<TemplateApiError>(error)) return error.response;
  if (error instanceof HandledRequestError) {
    return {
      status: error.status,
      data: error.payload as TemplateApiError | undefined,
    };
  }
  return undefined;
};

export default function TemplateEditor({ templateId }: TemplateEditorProps) {
  const { t } = useTranslation();
  const router = useScreenAwareRouter();
  const [form] = Form.useForm();
  const [messageApi, messageContextHolder] = message.useMessage();
  const api = useSettingApi();
  const { getAlarmList } = useAlarmApi();
  const { userList } = useCommon();
  const { username } = useUserInfoContext();
  const [loading, setLoading] = useState(!!templateId);
  const [detailReady, setDetailReady] = useState(!templateId);
  const [detailLoadFailed, setDetailLoadFailed] = useState(false);
  const [reloadToken, setReloadToken] = useState(0);
  const [saving, setSaving] = useState(false);
  const [previewing, setPreviewing] = useState(false);
  const [revision, setRevision] = useState(1);
  const [team, setTeam] = useState<number[]>([]);
  const [templateScope, setTemplateScope] = useState<NotificationTemplateItem['scope']>('single_alert');
  const [channelId, setChannelId] = useState<number>();
  const [activeChannel, setActiveChannel] = useState('email');
  const [contents, setContents] = useState<NotificationTemplateContent[]>([DEFAULT_CONTENTS[0]]);
  const [preview, setPreview] = useState<NotificationTemplatePreview>({ subject: '', body: '', missing_fields: [] });
  const [variables, setVariables] = useState<Array<{
    path: string;
    label: string;
    scopes?: NotificationTemplateItem['scope'][];
  }>>([]);
  const [channels, setChannels] = useState<Array<{
    id: number;
    name: string;
    channel_type: string;
    team?: Array<number | string>;
  }>>([]);
  const [testOpen, setTestOpen] = useState(false);
  const [testChannelId, setTestChannelId] = useState<number>();
  const [testAlertId, setTestAlertId] = useState<number>();
  const [testReceivers, setTestReceivers] = useState<string[]>(username ? [username] : []);
  const [testAlerts, setTestAlerts] = useState<AlarmTableDataItem[]>([]);
  const [testAlertsLoading, setTestAlertsLoading] = useState(false);
  const [testing, setTesting] = useState(false);
  const previewSequence = useRef(0);

  useEffect(() => {
    let active = true;
    const loadSupportingData = async () => {
      const [catalogResult, channelsResult] = await Promise.allSettled([
        api.getNotificationTemplateCatalog(),
        api.getChannelList({}),
      ]);
      if (!active) return;
      if (catalogResult.status === 'fulfilled') {
        setVariables(catalogResult.value.variables || []);
      }
      if (channelsResult.status === 'fulfilled') {
        setChannels(channelsResult.value || []);
      }
    };
    const loadDetail = async () => {
      if (!templateId) return;
      setLoading(true);
      setDetailReady(false);
      setDetailLoadFailed(false);
      try {
        const item: NotificationTemplateItem = await api.getNotificationTemplate(templateId);
        if (!active) return;
        form.setFieldsValue({ name: item.name, description: item.description });
        setRevision(item.revision);
        setTeam(item.team);
        setTemplateScope(item.scope);
        setChannelId(item.channel_id || undefined);
        if (item.scope === 'alert_operation') setTestChannelId(item.channel_id || undefined);
        const loadedContents = item.scope === 'alert_operation'
          ? item.contents.map(formatLegacyAlertOperationContent)
          : item.contents;
        setContents(loadedContents);
        setActiveChannel(loadedContents[0]?.channel_type || 'email');
        setDetailReady(true);
      } catch {
        if (!active) return;
        setDetailLoadFailed(true);
        messageApi.error(t('common.loadFailed'));
      } finally {
        if (active) setLoading(false);
      }
    };
    void loadSupportingData();
    void loadDetail();
    return () => {
      active = false;
    };
  }, [templateId, reloadToken]);

  const activeContent = useMemo(
    () => contents.find((item) => item.channel_type === activeChannel) || DEFAULT_CONTENTS[0],
    [activeChannel, contents],
  );
  const activeChannelConfig = getNotificationTemplateChannel(activeChannel) || NOTIFICATION_TEMPLATE_CHANNELS[0];
  const isOperationTemplate = templateScope === 'alert_operation';
  const visibleVariables = useMemo(
    () => variables.filter((variable) => !variable.scopes || variable.scopes.includes(templateScope)),
    [templateScope, variables],
  );
  const operationChannels = useMemo(
    () => channels.filter((channel) => !channel.team
      || channel.team.some((channelTeam) => team.includes(Number(channelTeam)))),
    [channels, team],
  );
  const testChannelOptions = useMemo(
    () => channels
      .filter((channel) => isOperationTemplate
        ? channel.id === channelId
        : contents.some((content) => content.channel_type === channel.channel_type))
      .map((channel) => ({ label: channel.name, value: channel.id })),
    [channelId, channels, contents, isOperationTemplate],
  );
  const testReceiverOptions = useMemo(
    () => userList.map((user) => {
      const displayName = typeof user.display_name === 'string' ? user.display_name : '';
      return {
        label: displayName ? `${displayName} (${user.username})` : user.username,
        value: user.username,
      };
    }),
    [userList],
  );

  useEffect(() => {
    if (!username) return;
    setTestReceivers((current) => current.length > 0 ? current : [username]);
  }, [username]);

  useEffect(() => {
    if (!testOpen || testChannelOptions.length === 0) return;
    setTestChannelId((current) => {
      if (testChannelOptions.some((option) => option.value === current)) return current;
      const activeChannelId = channels.find((channel) => channel.channel_type === activeChannel)?.id;
      return testChannelOptions.find((option) => option.value === activeChannelId)?.value
        || testChannelOptions[0].value;
    });
  }, [activeChannel, channels, testChannelOptions, testOpen]);

  const updateContent = (patch: Partial<NotificationTemplateContent>) => {
    setContents((current) => current.map((item) => item.channel_type === activeChannel ? { ...item, ...patch } : item));
  };

  const updateChannels = (selected: string[]) => {
    if (selected.length === 0) {
      messageApi.warning(t('settings.notificationTemplate.selectAtLeastOneChannel'));
      return;
    }
    setContents((current) => selected.map((channelType) => (
      current.find((item) => item.channel_type === channelType)
      || DEFAULT_CONTENTS.find((item) => item.channel_type === channelType)
      || { channel_type: channelType, subject_template: '', body_template: '' }
    )));
    if (!selected.includes(activeChannel)) setActiveChannel(selected[0]);
  };

  const updateOperationChannel = (selectedChannelId: number) => {
    const channel = operationChannels.find((item) => item.id === selectedChannelId);
    if (!channel) return;
    const nextContent = contents.find((item) => item.channel_type === channel.channel_type)
      || DEFAULT_ALERT_OPERATION_TEMPLATE_CONTENTS.find((item) => item.channel_type === channel.channel_type)
      || { channel_type: channel.channel_type, subject_template: '', body_template: '' };
    setChannelId(selectedChannelId);
    setTestChannelId(selectedChannelId);
    setContents([nextContent]);
    setActiveChannel(channel.channel_type);
  };

  const refreshPreview = async () => {
    if (!detailReady) return;
    const sequence = ++previewSequence.current;
    setPreviewing(true);
    try {
      const result = await api.previewNotificationTemplate({
        scope: templateScope,
        ...(isOperationTemplate ? { channel_id: channelId } : {}),
        channel_type: activeChannel,
        subject_template: activeContent.subject_template,
        body_template: activeContent.body_template,
      });
      if (sequence === previewSequence.current) setPreview(result);
    } catch (error: unknown) {
      if (sequence === previewSequence.current) {
        messageApi.error(getApiError(error)?.data?.detail || t('alarmCommon.operateFailed'));
      }
    } finally {
      if (sequence === previewSequence.current) setPreviewing(false);
    }
  };

  useEffect(() => {
    if (!detailReady) return;
    const timer = window.setTimeout(() => void refreshPreview(), 350);
    return () => {
      window.clearTimeout(timer);
      previewSequence.current += 1;
    };
  }, [activeChannel, activeContent.subject_template, activeContent.body_template, detailReady]);

  const save = async () => {
    if (!detailReady) return;
    const values = await form.validateFields();
    setSaving(true);
    try {
      const payload: NotificationTemplatePayload = {
        ...values,
        ...(templateId ? { team } : {}),
        scope: templateScope,
        ...(isOperationTemplate ? { channel_id: channelId } : {}),
        revision,
        contents,
      };
      if (templateId) {
        await api.updateNotificationTemplate(templateId, payload);
      } else {
        await api.createNotificationTemplate(payload);
      }
      messageApi.success(t('settings.notificationTemplate.saveSuccess'));
      router.push('/alarm/settings/notificationTemplates');
    } catch (error: unknown) {
      const response = getApiError(error);
      if (response?.status === 409) {
        messageApi.error(response.data?.revision || t('alarmCommon.operateFailed'));
      } else {
        messageApi.error(
          response?.data?.contents?.[0]?.detail
          || response?.data?.detail
          || (error instanceof Error ? error.message : '')
          || t('alarmCommon.operateFailed'),
        );
      }
    } finally {
      setSaving(false);
    }
  };

  const previewHtml = activeChannelConfig.previewMode === 'html'
    ? DOMPurify.sanitize(preview.body)
    : activeChannelConfig.previewMode === 'markdown'
      ? DOMPurify.sanitize(markdown.render(preview.body))
      : `<pre>${markdown.utils.escapeHtml(preview.body)}</pre>`;
  const previewDocument = `<!doctype html><html><head><meta charset="utf-8"><meta http-equiv="Content-Security-Policy" content="default-src 'none'; style-src 'unsafe-inline'"></head><body>${previewHtml}</body></html>`;

  const openTestModal = async () => {
    const activeChannelId = channels.find((channel) => channel.channel_type === activeChannel)?.id;
    if (!testChannelOptions.some((option) => option.value === testChannelId)) {
      setTestChannelId(
        testChannelOptions.find((option) => option.value === activeChannelId)?.value
        || testChannelOptions[0]?.value,
      );
    }
    setTestOpen(true);
    setTestAlertsLoading(true);
    try {
      const result = await getAlarmList({ page: 1, page_size: 50 });
      const items = result?.items || [];
      setTestAlerts(items);
      setTestAlertId((current) => items.some((item: AlarmTableDataItem) => item.id === current)
        ? current
        : undefined);
    } catch {
      setTestAlerts([]);
      messageApi.error(t('settings.notificationTemplate.testAlertLoadFailed'));
    } finally {
      setTestAlertsLoading(false);
    }
  };

  const testSend = async () => {
    if (!testChannelId || !testAlertId || testReceivers.length === 0) return;
    const selectedChannel = channels.find((channel) => channel.id === testChannelId);
    const selectedContent = contents.find((content) => content.channel_type === selectedChannel?.channel_type);
    if (!selectedChannel || !selectedContent) return;
    setTesting(true);
    try {
      await api.testSendDraftNotificationTemplate({
        ...(templateId ? { template_id: Number(templateId) } : {}),
        channel_id: testChannelId,
        alert_id: testAlertId,
        receivers: testReceivers,
        scope: templateScope,
        channel_type: selectedChannel.channel_type,
        subject_template: selectedContent.subject_template,
        body_template: selectedContent.body_template,
      });
      messageApi.success(t('settings.notificationTemplate.testSuccess'));
      setTestOpen(false);
    } catch (error: unknown) {
      const data = getApiError(error)?.data;
      messageApi.error(
        data?.alert_id
        || data?.receivers
        || data?.channel_id
        || data?.channel_type
        || data?.template_id
        || data?.detail
        || t('alarmCommon.operateFailed'),
      );
    } finally {
      setTesting(false);
    }
  };

  return (
    <>
      {messageContextHolder}
      <Spin spinning={loading}>
        <div className="flex min-h-[calc(100vh-160px)] flex-col gap-4 p-4">
          <div className="flex flex-col gap-3 lg:flex-row lg:items-start lg:justify-between">
            <div className="flex min-w-0 flex-wrap items-start gap-3">
              <Button
                icon={<ArrowLeftOutlined aria-hidden="true" />}
                aria-label={t('settings.notificationTemplate.backToTemplates')}
                onClick={() => router.push('/alarm/settings/notificationTemplates')}
              >
                {t('settings.notificationTemplate.backToTemplates')}
              </Button>
              <div className="min-w-0">
                <Space size={8} wrap>
                  <Typography.Title level={4} className="!mb-0">
                    {isOperationTemplate
                      ? t('settings.notificationTemplate.operationEditorTitle')
                      : templateId ? t('settings.notificationTemplate.editorTitle') : t('settings.notificationTemplate.createTitle')}
                  </Typography.Title>
                  {isOperationTemplate && (
                    <Tag color="blue">{t('settings.notificationTemplate.builtinTemplate')}</Tag>
                  )}
                </Space>
                {isOperationTemplate && (
                  <Typography.Text type="secondary" className="mt-1 block">
                    {t('settings.notificationTemplate.operationEditorDescription')}
                  </Typography.Text>
                )}
              </div>
            </div>
            <Space wrap>
              <Button disabled={!detailReady} onClick={() => void openTestModal()}>
                {t('settings.notificationTemplate.testSend')}
              </Button>
              <Button disabled={!detailReady} icon={<EyeOutlined />} loading={previewing} onClick={() => void refreshPreview()}>
                {t('settings.notificationTemplate.refreshPreview')}
              </Button>
              <Button disabled={!detailReady} type="primary" icon={<SaveOutlined />} loading={saving} onClick={() => void save()}>
                {t('common.save')}
              </Button>
            </Space>
          </div>

          {detailLoadFailed && (
            <Alert
              type="error"
              showIcon
              message={t('common.loadFailed')}
              action={<Button size="small" onClick={() => setReloadToken((value) => value + 1)}>{t('common.retry')}</Button>}
            />
          )}

          {detailReady && <>
          <Modal
            open={testOpen}
            title={t('settings.notificationTemplate.testSend')}
            okButtonProps={{
              loading: testing,
              disabled: !testChannelId || !testAlertId || testReceivers.length === 0,
            }}
            onOk={() => void testSend()}
            onCancel={() => setTestOpen(false)}
          >
            <div className="flex flex-col gap-4 py-3">
              <div className="flex flex-col gap-2">
                <Typography.Text strong>{t('settings.notificationTemplate.testAlert')}</Typography.Text>
                <Select
                  aria-label={t('settings.notificationTemplate.testAlert')}
                  showSearch
                  optionFilterProp="label"
                  loading={testAlertsLoading}
                  placeholder={t('settings.notificationTemplate.testAlertPlaceholder')}
                  value={testAlertId}
                  onChange={setTestAlertId}
                  options={testAlerts.map((alert) => ({
                    label: `[${alert.alert_id}] ${alert.title}${alert.resource_name ? ` · ${alert.resource_name}` : ''}`,
                    value: alert.id,
                  }))}
                  notFoundContent={testAlertsLoading
                    ? <Spin size="small" />
                    : t('settings.notificationTemplate.noTestAlerts')}
                />
                <Typography.Text type="secondary">
                  {t('settings.notificationTemplate.testAlertHint')}
                </Typography.Text>
              </div>
              <div className="flex flex-col gap-2">
                <Typography.Text strong>{t('settings.notificationTemplate.testReceivers')}</Typography.Text>
                <Select
                  aria-label={t('settings.notificationTemplate.testReceivers')}
                  mode="multiple"
                  showSearch
                  optionFilterProp="label"
                  maxTagCount="responsive"
                  placeholder={t('settings.notificationTemplate.testReceiversPlaceholder')}
                  value={testReceivers}
                  onChange={setTestReceivers}
                  options={testReceiverOptions}
                />
                <Typography.Text type="secondary">
                  {t('settings.notificationTemplate.testReceiversHint')}
                </Typography.Text>
              </div>
              <div className="flex flex-col gap-2">
                <Typography.Text strong>{t('settings.notificationTemplate.testChannel')}</Typography.Text>
              <Select
                aria-label={t('settings.notificationTemplate.testChannel')}
                placeholder={t('settings.notificationTemplate.testChannel')}
                value={testChannelId}
                disabled={isOperationTemplate}
                onChange={setTestChannelId}
                options={testChannelOptions}
              />
              <Typography.Text type="secondary">
                {t('settings.notificationTemplate.testTargetHint')}
              </Typography.Text>
              </div>
            </div>
          </Modal>

          <Card
            size="small"
            title={t(isOperationTemplate
              ? 'settings.notificationTemplate.notificationSettings'
              : 'settings.notificationTemplate.basicInfo')}
          >
            <Form form={form} layout="vertical">
              {isOperationTemplate ? (
                <>
                  <Form.Item name="name" hidden><Input /></Form.Item>
                  <Form.Item name="description" hidden><Input /></Form.Item>
                </>
              ) : (
                <div className="grid grid-cols-1 gap-x-4 lg:grid-cols-2">
                  <Form.Item name="name" label={t('settings.notificationTemplate.name')} rules={[{ required: true }]}>
                    <Input maxLength={100} />
                  </Form.Item>
                  <Form.Item name="description" label={t('settings.notificationTemplate.description')}>
                    <Input maxLength={500} />
                  </Form.Item>
                </div>
              )}
              {isOperationTemplate ? (
                <Form.Item
                  required
                  label={t('settings.notificationTemplate.operationChannel')}
                  className="!mb-3"
                >
                  <Select
                    className="w-full"
                    value={channelId}
                    placeholder={t('settings.notificationTemplate.operationChannelPlaceholder')}
                    options={operationChannels.map((channel) => ({ label: channel.name, value: channel.id }))}
                    onChange={updateOperationChannel}
                  />
                </Form.Item>
              ) : (
                <Form.Item label={t('settings.notificationTemplate.channels')} className="!mb-3">
                  <Select
                    mode="multiple"
                    className="w-full"
                    value={contents.map((item) => item.channel_type)}
                    options={NOTIFICATION_TEMPLATE_CHANNELS.map((channel) => ({ value: channel.key, label: t(channel.labelKey) }))}
                    onChange={updateChannels}
                  />
                </Form.Item>
              )}
              <Alert
                type="info"
                showIcon
                message={t(isOperationTemplate
                  ? 'settings.notificationTemplate.operationChannelHint'
                  : 'settings.notificationTemplate.channelVersionHint')}
              />
            </Form>
          </Card>

          <div className="grid min-h-0 flex-1 grid-cols-1 gap-4 xl:grid-cols-2">
            <Card className="min-h-0" styles={{ body: { height: '100%' } }}>
              <div className="flex flex-wrap items-center justify-between gap-2">
                <Typography.Text strong>{t('settings.notificationTemplate.contentEditor')}</Typography.Text>
                <Space size={4}>
                  <Typography.Text type="secondary">
                    {t('settings.notificationTemplate.editingVersion')}：{t(activeChannelConfig.labelKey)}
                  </Typography.Text>
                  <Tag>
                    {activeChannelConfig.editorMode === 'html'
                      ? 'HTML'
                      : activeChannelConfig.editorMode === 'markdown'
                        ? 'Markdown'
                        : 'Text'}
                  </Tag>
                </Space>
              </div>
              {isOperationTemplate ? <div className="my-3"><Tag>{t(activeChannelConfig.labelKey)}</Tag></div> : (
                <Tabs
                  activeKey={activeChannel}
                  onChange={setActiveChannel}
                  items={contents.map((content) => {
                    const channel = getNotificationTemplateChannel(content.channel_type) || NOTIFICATION_TEMPLATE_CHANNELS[0];
                    return { key: content.channel_type, label: t(channel.labelKey) };
                  })}
                />
              )}
              <div className="mb-3 flex flex-wrap items-center gap-2">
                <Typography.Text type="secondary">{t('settings.notificationTemplate.variables')}：</Typography.Text>
                {visibleVariables.map((variable) => (
                  <Tag
                    key={variable.path}
                    className="cursor-pointer"
                    onClick={() => updateContent({ body_template: `${activeContent.body_template}{{ ${variable.path} }}` })}
                  >
                    {variable.label}
                  </Tag>
                ))}
              </div>
              {activeChannelConfig.hasSubject && (
                <div className="mb-3">
                  <Typography.Text>{t('settings.notificationTemplate.subject')}</Typography.Text>
                  <Input
                    className="mt-1"
                    value={activeContent.subject_template}
                    maxLength={200}
                    onChange={(event) => updateContent({ subject_template: event.target.value })}
                  />
                </div>
              )}
              <Typography.Text>{t('settings.notificationTemplate.body')}</Typography.Text>
              <AceEditor
                className="mt-1 overflow-hidden rounded border border-[var(--color-border-2)]"
                mode={activeChannelConfig.editorMode}
                theme="github"
                width="100%"
                height="clamp(360px, calc(100vh - 570px), 640px)"
                value={activeContent.body_template}
                onChange={(value) => updateContent({ body_template: value })}
                wrapEnabled
                setOptions={{ showPrintMargin: false, useWorker: false, tabSize: 2 }}
              />
            </Card>

            <Card
              title={t('settings.notificationTemplate.preview')}
              className="min-h-0"
              extra={<Tag>{activeChannelConfig.editorMode === 'html' ? 'HTML' : activeChannelConfig.editorMode === 'markdown' ? 'Markdown' : 'Text'}</Tag>}
            >
              {preview.subject && <Typography.Title level={5}>{preview.subject}</Typography.Title>}
              {preview.missing_fields.length > 0 && (
                <Alert
                  className="mb-3"
                  type="warning"
                  showIcon
                  message={`${t('settings.notificationTemplate.missing')}：${preview.missing_fields.join(', ')}`}
                />
              )}
              <iframe
                title={t('settings.notificationTemplate.preview')}
                sandbox=""
                referrerPolicy="no-referrer"
                srcDoc={previewDocument}
                className="h-[calc(100vh-380px)] min-h-[520px] max-h-[800px] w-full rounded border border-[var(--color-border-2)] bg-[var(--color-bg-1)]"
              />
            </Card>
          </div>
          </>}
        </div>
      </Spin>
    </>
  );
}
