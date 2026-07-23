'use client';

import { useEffect, useMemo, useRef, useState } from 'react';
import { Alert, Button, Empty, Form, Input, List, Modal, Select, Skeleton, Switch } from 'antd';
import { useTranslation } from '@/utils/i18n';
import type {
  CreateIncidentIMGroupParams,
  IncidentIMGroupOptions,
} from '@/app/alarm/types/incidents';
import {
  canSubmitIMGroupCreation,
  isChannelOptionsCurrent,
  shouldInitializeCreateForm,
} from './controller';

interface CreateIMGroupModalProps {
  open: boolean;
  options: IncidentIMGroupOptions | null;
  optionsChannelId?: number;
  optionsError: unknown | null;
  loading: boolean;
  submitting: boolean;
  onLoadOptions: (channelId?: number) => Promise<IncidentIMGroupOptions>;
  onSubmit: (params: CreateIncidentIMGroupParams) => Promise<void>;
  onCancel: () => void;
}

export const CreateIMGroupModal = ({
  open,
  options,
  optionsChannelId,
  optionsError,
  loading,
  submitting,
  onLoadOptions,
  onSubmit,
  onCancel,
}: CreateIMGroupModalProps) => {
  const { t } = useTranslation();
  const [form] = Form.useForm<CreateIncidentIMGroupParams>();
  const channelId = Form.useWatch('channel_id', form);
  const groupName = Form.useWatch('group_name', form);
  const ownerUsername = Form.useWatch('owner_username', form);
  const contextualOptions = channelId !== undefined
    && optionsChannelId !== undefined
    && isChannelOptionsCurrent(channelId, optionsChannelId)
    ? options
    : null;
  const members = contextualOptions?.members ?? [];
  const mappedCount = members.filter(member => member.mapping_status === 'mapped').length;
  const conflictCount = members.filter(member => member.mapping_status === 'conflict').length;
  const unmappedCount = members.filter(member => member.mapping_status === 'unmapped').length;
  const canSubmit = canSubmitIMGroupCreation(
    contextualOptions,
    channelId,
    groupName,
    ownerUsername,
  );
  const wasOpenRef = useRef(false);
  const channelRequestRef = useRef(0);
  const [previewError, setPreviewError] = useState<unknown | null>(null);
  const [previewExpanded, setPreviewExpanded] = useState(false);

  useEffect(() => {
    const opening = shouldInitializeCreateForm(wasOpenRef.current, open);
    wasOpenRef.current = open;
    if (!opening || !options) return;
    const firstChannel = options.channels[0]?.id;
    form.resetFields();
    form.setFieldsValue({
      channel_id: firstChannel,
      group_name: options.default_group_name,
      continuous_sync_enabled: true,
    });
    setPreviewError(null);
    setPreviewExpanded(false);
    if (firstChannel !== undefined) void loadChannelPreview(firstChannel);
    // Opening is the only event allowed to initialise user-editable fields.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [form, onLoadOptions, open, options]);

  const previewItems = useMemo(
    () => previewExpanded ? members : members.slice(0, 5),
    [members, previewExpanded],
  );

  const handleChannelChange = async (nextChannelId: number) => {
    form.setFieldValue('owner_username', undefined);
    await loadChannelPreview(nextChannelId);
  };

  const loadChannelPreview = async (requestedChannelId: number) => {
    channelRequestRef.current += 1;
    const requestGeneration = channelRequestRef.current;
    setPreviewError(null);
    try {
      const next = await onLoadOptions(requestedChannelId);
      if (
        requestGeneration === channelRequestRef.current
        && isChannelOptionsCurrent(form.getFieldValue('channel_id'), requestedChannelId)
      ) {
        form.setFieldValue('owner_username', next.owner_candidates?.[0]?.username);
      }
    } catch (error) {
      if (
        requestGeneration === channelRequestRef.current
        && isChannelOptionsCurrent(form.getFieldValue('channel_id'), requestedChannelId)
      ) {
        setPreviewError(error);
      }
    }
  };

  return (
    <Modal
      title={t('incidents.imGroup.createTitle')}
      open={open}
      width={600}
      maskClosable={!submitting}
      closable={!submitting}
      keyboard={!submitting}
      confirmLoading={submitting}
      okButtonProps={{ disabled: !canSubmit }}
      okText={t('incidents.imGroup.create')}
      cancelText={t('common.cancel')}
      onCancel={onCancel}
      onOk={() => {
        void form.validateFields().then(onSubmit);
      }}
      styles={{ body: { maxHeight: 'calc(100vh - 240px)', overflowY: 'auto' } }}
      destroyOnHidden
    >
      {options && options.channels.length === 0 ? (
        <Empty description={t('incidents.imGroup.noChannels')}>
          <Button href="/system-manager/channel/im-notification" target="_blank">
            {t('incidents.imGroup.configureChannels')}
          </Button>
        </Empty>
      ) : (
        <Form form={form} layout="vertical" requiredMark>
          <Form.Item
            name="channel_id"
            label={t('incidents.imGroup.channel')}
            rules={[{ required: true, message: t('incidents.imGroup.channelRequired') }]}
          >
            <Select
              size="large"
              loading={loading}
              options={options?.channels.map(channel => ({ label: channel.name, value: channel.id }))}
              onChange={handleChannelChange}
            />
          </Form.Item>
          <Form.Item
            name="group_name"
            label={t('incidents.imGroup.groupName')}
            rules={[{ required: true, whitespace: true, message: t('incidents.imGroup.groupNameRequired') }]}
          >
            <Input size="large" maxLength={255} showCount />
          </Form.Item>
          <Form.Item
            name="owner_username"
            label={t('incidents.imGroup.owner')}
            extra={
              channelId && !loading && !contextualOptions?.owner_candidates?.length
                ? t('incidents.imGroup.ownerRequiredHint')
                : undefined
            }
            rules={[{ required: true, message: t('incidents.imGroup.ownerRequired') }]}
          >
            <Select
              size="large"
              loading={loading}
              disabled={!channelId || loading}
              options={contextualOptions?.owner_candidates?.map(owner => ({
                label: `${owner.display_name} (${owner.username})`,
                value: owner.username,
              }))}
            />
          </Form.Item>

          <div className="mb-4" aria-live="polite">
            <div className="text-sm font-medium mb-2">{t('incidents.imGroup.memberPreview')}</div>
            <Skeleton loading={loading} active paragraph={{ rows: 2 }}>
              {(previewError || optionsError) && (
                <Alert
                  className="mb-2"
                  type="error"
                  showIcon
                  message={t('incidents.imGroup.previewLoadFailed')}
                  action={
                    channelId ? (
                      <Button
                        type="link"
                        size="small"
                        onClick={() => void loadChannelPreview(channelId)}
                      >
                        {t('common.retry')}
                      </Button>
                    ) : undefined
                  }
                />
              )}
              <div className="text-xs text-[var(--color-text-3)] mb-2 tabular-nums">
                {t('incidents.imGroup.previewSummary', undefined, {
                  mapped: String(mappedCount),
                  unmapped: String(unmappedCount),
                  conflict: String(conflictCount),
                })}
              </div>
              {(unmappedCount > 0 || conflictCount > 0) && (
                <Alert
                  className="mb-2"
                  type="warning"
                  showIcon
                  message={t('incidents.imGroup.partialMappingWarning')}
                />
              )}
              <List
                size="small"
                dataSource={previewItems}
                locale={{ emptyText: t('common.noData') }}
                renderItem={member => (
                  <List.Item>
                    <span className="min-w-0 truncate">{member.display_name} ({member.username})</span>
                    <span className="text-xs text-[var(--color-text-3)]">
                      {t(`incidents.imGroup.mapping.${member.mapping_status}`)}
                    </span>
                  </List.Item>
                )}
              />
              {members.length > 5 && (
                <Button
                  type="link"
                  size="small"
                  aria-expanded={previewExpanded}
                  onClick={() => setPreviewExpanded(value => !value)}
                >
                  {previewExpanded
                    ? t('incidents.imGroup.collapsePreview')
                    : t('incidents.imGroup.expandPreview', undefined, {
                      count: String(members.length - 5),
                    })}
                </Button>
              )}
            </Skeleton>
          </div>

          <Form.Item
            name="continuous_sync_enabled"
            label={t('incidents.imGroup.continuousSync')}
            valuePropName="checked"
          >
            <Switch />
          </Form.Item>
          <div className="text-xs text-[var(--color-text-3)] -mt-4">
            {t('incidents.imGroup.addOnlyHint')}
          </div>
        </Form>
      )}
    </Modal>
  );
};
