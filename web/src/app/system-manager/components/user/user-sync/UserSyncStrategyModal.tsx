import React, { useEffect } from 'react';
import { Button, Form, Switch, TimePicker } from 'antd';
import dayjs from 'dayjs';

import OperateModal from '@/components/operate-modal';
import type { UserSyncSource, UserSyncSourceStrategyFormValues } from '@/app/system-manager/types/user-sync';
import { parseScheduleConfig } from '@/app/system-manager/utils/userSyncUtils';

interface UserSyncStrategyModalProps {
  open: boolean;
  source: UserSyncSource | null;
  loading: boolean;
  t: (key: string, fallback?: string) => string;
  onClose: () => void;
  onSubmit: (values: UserSyncSourceStrategyFormValues) => void;
}

const UserSyncStrategyModal: React.FC<UserSyncStrategyModalProps> = ({
  open,
  source,
  loading,
  t,
  onClose,
  onSubmit,
}) => {
  const [form] = Form.useForm<UserSyncSourceStrategyFormValues>();

  useEffect(() => {
    if (!open || !source) return;
    const { scheduleEnabled, syncTime } = parseScheduleConfig(source.schedule_config);
    form.setFieldsValue({
      enabled: source.enabled,
      schedule_enabled: scheduleEnabled,
      sync_time: syncTime,
    });
  }, [open, source, form]);

  const handleSubmit = async () => {
    try {
      await form.validateFields();
    } catch {
      return;
    }
    onSubmit(form.getFieldsValue(true) as UserSyncSourceStrategyFormValues);
  };

  return (
    <OperateModal
    title={t('system.user.userSyncPage.syncStrategy')}
    subTitle={source?.name || ''}
    open={open}
    onCancel={onClose}
    width={560}
    footer={(
      <div className="flex justify-end gap-2">
        <Button onClick={onClose} disabled={loading}>
          {t('common.cancel')}
        </Button>
        <Button type="primary" onClick={handleSubmit} loading={loading}>
          {t('common.save')}
        </Button>
      </div>
    )}
    destroyOnClose
  >
    <Form form={form} layout="vertical">
      <div className="rounded-2xl border border-[var(--color-border)] bg-[var(--color-bg)] px-4 py-4">
        <div className="flex items-center justify-between gap-3">
          <div className="font-medium text-[var(--color-text)]">
            {t('system.user.userSyncPage.enabledLabel')}
          </div>
          <Form.Item name="enabled" valuePropName="checked" className="mb-0">
            <Switch />
          </Form.Item>
        </div>
      </div>

      <div className="mt-4 rounded-2xl border border-[var(--color-border)] bg-[var(--color-bg)] px-4 py-4">
        <div className="flex items-center justify-between gap-3">
          <div className="font-medium text-[var(--color-text)]">
            {t('system.user.userSyncPage.scheduleEnabled')}
          </div>
          <Form.Item name="schedule_enabled" valuePropName="checked" className="mb-0">
            <Switch />
          </Form.Item>
        </div>
        <Form.Item noStyle shouldUpdate={(prev, cur) => prev.schedule_enabled !== cur.schedule_enabled}>
          {({ getFieldValue }) =>
            getFieldValue('schedule_enabled') ? (
              <Form.Item
                name="sync_time"
                label={t('system.user.userSyncPage.syncTime')}
                required
                rules={[{ required: true }]}
                className="mb-0 mt-4"
                normalize={(val) => (val ? (dayjs.isDayjs(val) ? val.format('HH:mm') : val) : '')}
                getValueProps={(val) => ({ value: val ? dayjs(val, 'HH:mm') : null })}
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
};

export default UserSyncStrategyModal;
