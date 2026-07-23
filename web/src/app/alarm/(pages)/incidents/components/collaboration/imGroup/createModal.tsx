'use client';

import { useEffect, useMemo } from 'react';
import { Alert, Empty, Form, Input, List, Modal, Select, Skeleton, Switch } from 'antd';
import { useTranslation } from '@/utils/i18n';
import type {
  CreateIncidentIMGroupParams,
  IncidentIMGroupOptions,
} from '@/app/alarm/types/incidents';
import { canSubmitIMGroupCreation } from './controller';

interface CreateIMGroupModalProps {
  open: boolean;
  options: IncidentIMGroupOptions | null;
  loading: boolean;
  submitting: boolean;
  onLoadOptions: (channelId?: number) => Promise<IncidentIMGroupOptions>;
  onSubmit: (params: CreateIncidentIMGroupParams) => Promise<void>;
  onCancel: () => void;
}

export const CreateIMGroupModal = ({
  open,
  options,
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
  const members = options?.members ?? [];
  const mappedCount = members.filter(member => member.mapping_status === 'mapped').length;
  const conflictCount = members.filter(member => member.mapping_status === 'conflict').length;
  const unmappedCount = members.filter(member => member.mapping_status === 'unmapped').length;
  const canSubmit = canSubmitIMGroupCreation(options, channelId, groupName, ownerUsername);

  useEffect(() => {
    if (!open || !options) return;
    const firstChannel = options.channels[0]?.id;
    form.setFieldsValue({
      channel_id: firstChannel,
      group_name: options.default_group_name,
      continuous_sync_enabled: true,
    });
    if (firstChannel !== undefined && !options.members) {
      void onLoadOptions(firstChannel).then(next => {
        form.setFieldValue('owner_username', next.owner_candidates?.[0]?.username);
      });
    }
  }, [form, onLoadOptions, open, options]);

  const previewItems = useMemo(() => members.slice(0, 5), [members]);

  const handleChannelChange = async (nextChannelId: number) => {
    form.setFieldValue('owner_username', undefined);
    const next = await onLoadOptions(nextChannelId);
    form.setFieldValue('owner_username', next.owner_candidates?.[0]?.username);
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
        <Empty description={t('incidents.imGroup.noChannels')} />
      ) : (
        <Form form={form} layout="vertical" requiredMark>
          <Form.Item
            name="channel_id"
            label={t('incidents.imGroup.channel')}
            rules={[{ required: true, message: t('incidents.imGroup.channelRequired') }]}
          >
            <Select
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
            <Input maxLength={255} showCount />
          </Form.Item>
          <Form.Item
            name="owner_username"
            label={t('incidents.imGroup.owner')}
            extra={
              channelId && !loading && !options?.owner_candidates?.length
                ? t('incidents.imGroup.ownerRequiredHint')
                : undefined
            }
            rules={[{ required: true, message: t('incidents.imGroup.ownerRequired') }]}
          >
            <Select
              loading={loading}
              disabled={!channelId || loading}
              options={options?.owner_candidates?.map(owner => ({
                label: `${owner.display_name} (${owner.username})`,
                value: owner.username,
              }))}
            />
          </Form.Item>

          <div className="mb-4" aria-live="polite">
            <div className="text-sm font-medium mb-2">{t('incidents.imGroup.memberPreview')}</div>
            <Skeleton loading={loading} active paragraph={{ rows: 2 }}>
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
              {members.length > previewItems.length && (
                <div className="text-xs text-[var(--color-text-3)]">
                  {t('incidents.imGroup.moreMembers', undefined, {
                    count: String(members.length - previewItems.length),
                  })}
                </div>
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
