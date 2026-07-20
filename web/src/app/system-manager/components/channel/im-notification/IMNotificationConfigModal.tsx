import React from 'react';
import dayjs from 'dayjs';
import { Alert, Form, Input, Select, TimePicker } from 'antd';
import type { FormInstance } from 'antd';

import OperateModal from '@/components/operate-modal';
import type {
  AvailableInstance,
  IMNotificationChannel,
  IMNotificationChannelPayload,
} from '@/app/system-manager/types/im-notification';
import { formatIntegrationInstanceDisplayName } from '@/app/system-manager/utils/integrationCenter';

export interface IMNotificationChannelFormValues extends IMNotificationChannelPayload {
  schedule_enabled?: boolean;
  sync_time?: string;
}

interface IMNotificationConfigModalProps {
  open: boolean;
  editing: IMNotificationChannel | null;
  loading: boolean;
  form: FormInstance<IMNotificationChannelFormValues>;
  availableInstances: AvailableInstance[];
  platformMatchOptions: Array<{ value: string; label: string }>;
  externalMatchOptions: Array<{ value: string; label: string }>;
  externalReceiveOptions: Array<{ value: string; label: string }>;
  manifestHintVisible: boolean;
  showMatchFieldHint: boolean;
  showReceiveFieldHint: boolean;
  t: (key: string, defaultMessage?: string, values?: Record<string, string | number>) => string;
  onOk: () => void;
  onCancel: () => void;
}

const IMNotificationConfigModal: React.FC<IMNotificationConfigModalProps> = ({
  open,
  editing,
  loading,
  form,
  availableInstances,
  platformMatchOptions,
  externalMatchOptions,
  externalReceiveOptions,
  manifestHintVisible,
  showMatchFieldHint,
  showReceiveFieldHint,
  t,
  onOk,
  onCancel,
}) => (
  <OperateModal
    title={editing ? t('common.edit') : t('common.add')}
    open={open}
    onOk={onOk}
    onCancel={onCancel}
    confirmLoading={loading}
    width={640}
  >
    <Form form={form} layout="vertical">
      <div className="mb-6">
        <div className="mb-2 text-[16px] font-semibold text-[var(--color-text-1)]">
          {t('system.channel.imNotificationPage.basicInfoTitle')}
        </div>
        <div className="mb-5 text-[13px] text-[var(--color-text-3)]">
          {t('system.channel.imNotificationPage.basicInfoDesc')}
        </div>
        <Form.Item name="name" label={t('system.channel.imNotificationPage.name')} rules={[{ required: true, whitespace: true }]}>
          <Input placeholder={t('system.channel.imNotificationPage.namePlaceholder')} />
        </Form.Item>
        <Form.Item
          name="integration_instance"
          label={t('system.channel.imNotificationPage.integrationInstance')}
          rules={[{ required: true }]}
        >
          <Select
            placeholder={t('system.channel.imNotificationPage.integrationInstancePlaceholder')}
            options={availableInstances.map((instance) => ({
              value: instance.id,
              label: formatIntegrationInstanceDisplayName(instance, t),
            }))}
          />
        </Form.Item>
        <Form.Item name="description" label={t('system.channel.imNotificationPage.description')}>
          <Input.TextArea rows={3} placeholder={t('system.channel.imNotificationPage.descriptionPlaceholder')} />
        </Form.Item>
      </div>

      <div className="border-t border-[var(--color-border-1)] pt-6">
        <div className="mb-2 text-[16px] font-semibold text-[var(--color-text-1)]">
          {t('system.channel.imNotificationPage.fieldMappingTitle')}
        </div>
        <div className="mb-5 text-[13px] text-[var(--color-text-3)]">
          {t('system.channel.imNotificationPage.fieldMappingDesc')}
        </div>
        {manifestHintVisible ? (
          <Alert
            className="mb-4"
            type="warning"
            showIcon
            message={t('system.channel.imNotificationPage.manifestNotFound')}
          />
        ) : null}
        <div className="rounded-2xl border border-[var(--color-border)] bg-[var(--color-bg)] px-4 py-4">
          <div className="grid grid-cols-[minmax(0,1fr)_24px_minmax(0,1fr)] gap-x-4 gap-y-3 text-[13px] text-[var(--color-text-3)]">
            <div>{t('system.channel.imNotificationPage.platformMatchField')}</div>
            <div />
            <div>{t('system.channel.imNotificationPage.externalMatchField')}</div>
          </div>
          <div className="mt-3 grid grid-cols-[minmax(0,1fr)_24px_minmax(0,1fr)] gap-x-4 gap-y-3">
            <Form.Item name="platform_match_field" rules={[{ required: true, message: t('common.selectMsg') }]} className="mb-0">
              <Select options={platformMatchOptions} />
            </Form.Item>
            <div className="flex h-10 items-center justify-center text-lg text-[var(--color-primary)]">=</div>
            <Form.Item name="external_match_field" rules={[{ required: true, message: t('common.selectMsg') }]} className="mb-0">
              <Select
                options={externalMatchOptions}
                disabled={externalMatchOptions.length === 0}
                placeholder={t('system.channel.imNotificationPage.externalMatchFieldPlaceholder')}
              />
            </Form.Item>
          </div>
          {showMatchFieldHint ? (
            <div className="mt-3 text-[12px] text-[var(--color-text-3)]">
              {t('system.channel.imNotificationPage.matchFieldUnavailableHint')}
            </div>
          ) : null}
          <div className="mt-5">
            <Form.Item
              name="external_receive_field"
              label={t('system.channel.imNotificationPage.receiveField')}
              rules={[{ required: true, message: t('common.selectMsg') }]}
              className="mb-0"
            >
              <Select
                options={externalReceiveOptions}
                disabled={externalReceiveOptions.length === 0}
                placeholder={t('system.channel.imNotificationPage.externalReceiveFieldPlaceholder')}
              />
            </Form.Item>
            <div className="mt-3 text-[12px] text-[var(--color-text-3)]">
              {t('system.channel.imNotificationPage.receiveFieldHint')}
            </div>
            {showReceiveFieldHint ? (
              <div className="mt-3 text-[12px] text-[var(--color-text-3)]">
                {t('system.channel.imNotificationPage.receiveFieldUnavailableHint')}
              </div>
            ) : null}
          </div>
        </div>
      </div>

      <div className="border-t border-[var(--color-border-1)] pt-6">
        <div className="mb-2 text-[16px] font-semibold text-[var(--color-text-1)]">
          {t('system.channel.imNotificationPage.syncOptionsTitle')}
        </div>
        <div className="mb-5 text-[13px] text-[var(--color-text-3)]">
          {t('system.channel.imNotificationPage.syncOptionsDesc')}
        </div>
        <Form.Item name="schedule_enabled" label={t('system.channel.imNotificationPage.syncMode')} className="mb-0">
          <Select
            options={[
              { label: t('system.channel.imNotificationPage.syncModeManual'), value: false },
              { label: t('system.channel.imNotificationPage.syncModeAutomatic'), value: true },
            ]}
          />
        </Form.Item>
        <Form.Item noStyle shouldUpdate={(prev, cur) => prev.schedule_enabled !== cur.schedule_enabled}>
          {({ getFieldValue }) =>
            getFieldValue('schedule_enabled') ? (
              <Form.Item
                name="sync_time"
                label={t('system.channel.imNotificationPage.syncTime')}
                required
                rules={[{ required: true }]}
                className="mb-0 mt-5"
                normalize={(value) => (value ? (dayjs.isDayjs(value) ? value.format('HH:mm') : value) : '')}
                getValueProps={(value) => ({ value: value ? dayjs(value, 'HH:mm') : null })}
              >
                <TimePicker format="HH:mm" className="w-full md:w-[220px]" />
              </Form.Item>
            ) : null
          }
        </Form.Item>
      </div>
    </Form>
  </OperateModal>
);

export default IMNotificationConfigModal;
