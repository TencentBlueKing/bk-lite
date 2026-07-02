import React, { useEffect } from 'react';
import { Button, Form, Select, Switch, TimePicker } from 'antd';
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

const WEEKDAY_OPTIONS = [1, 2, 3, 4, 5, 6, 7];
const INTERVAL_OPTIONS: Array<1 | 2 | 3 | 4 | 6 | 8 | 12> = [1, 2, 3, 4, 6, 8, 12];

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
    form.setFieldsValue({
      enabled: source.enabled,
      ...parseScheduleConfig(source.schedule_config),
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
        <div className="rounded-lg border border-[var(--color-border)] bg-[var(--color-bg)] px-4 py-4">
          <div className="flex items-center justify-between gap-3">
            <div>
              <div className="font-medium text-[var(--color-text)]">
                {t('system.user.userSyncPage.enabledLabel')}
              </div>
              <div className="mt-1 text-xs text-[var(--color-text-3)]">
                {t('system.user.userSyncPage.enabledHelp')}
              </div>
            </div>
            <Form.Item name="enabled" valuePropName="checked" className="mb-0">
              <Switch />
            </Form.Item>
          </div>
        </div>

        <div className="mt-4 rounded-lg border border-[var(--color-border)] bg-[var(--color-bg)] px-4 py-4">
          <Form.Item
            name="schedule_mode"
            label={t('system.user.userSyncPage.scheduleEnabled')}
            className="mb-0"
            rules={[{ required: true }]}
          >
            <Select
              options={[
                { value: 'disabled', label: t('system.user.userSyncPage.scheduleModeDisabled') },
                { value: 'daily', label: t('system.user.userSyncPage.scheduleModeDaily') },
                { value: 'weekly', label: t('system.user.userSyncPage.scheduleModeWeekly') },
                { value: 'interval_hours', label: t('system.user.userSyncPage.scheduleModeIntervalHours') },
              ]}
            />
          </Form.Item>

          <Form.Item noStyle shouldUpdate={(prev, cur) => prev.schedule_mode !== cur.schedule_mode}>
            {({ getFieldValue }) => {
              const mode = getFieldValue('schedule_mode');
              if (mode === 'daily') {
                return (
                  <Form.Item
                    name="time"
                    label={t('system.user.userSyncPage.syncTime')}
                    required
                    rules={[{ required: true }]}
                    className="mb-0 mt-4"
                    normalize={(val) => (val ? (dayjs.isDayjs(val) ? val.format('HH:mm') : val) : '')}
                    getValueProps={(val) => ({ value: val ? dayjs(val, 'HH:mm') : null })}
                  >
                    <TimePicker format="HH:mm" className="w-full md:w-[220px]" />
                  </Form.Item>
                );
              }

              if (mode === 'weekly') {
                return (
                  <>
                    <Form.Item
                      name="weekdays"
                      label={t('system.user.userSyncPage.weekdayLabel')}
                      rules={[{ required: true }]}
                      className="mb-0 mt-4"
                    >
                      <Select
                        mode="multiple"
                        options={WEEKDAY_OPTIONS.map((day) => ({
                          label: t(`system.user.userSyncPage.weekdays.${day}`),
                          value: day,
                        }))}
                      />
                    </Form.Item>
                    <Form.Item
                      name="time"
                      label={t('system.user.userSyncPage.syncTime')}
                      required
                      rules={[{ required: true }]}
                      className="mb-0 mt-4"
                      normalize={(val) => (val ? (dayjs.isDayjs(val) ? val.format('HH:mm') : val) : '')}
                      getValueProps={(val) => ({ value: val ? dayjs(val, 'HH:mm') : null })}
                    >
                      <TimePicker format="HH:mm" className="w-full md:w-[220px]" />
                    </Form.Item>
                  </>
                );
              }

              if (mode === 'interval_hours') {
                return (
                  <div className="mt-4">
                    <Form.Item
                      name="interval_hours"
                      label={t('system.user.userSyncPage.intervalHours')}
                      rules={[{ required: true }]}
                      className="mb-0"
                    >
                      <Select
                        options={INTERVAL_OPTIONS.map((hours) => ({
                          value: hours,
                          label: `${hours}`,
                        }))}
                      />
                    </Form.Item>
                    <div className="mt-2 text-xs text-[var(--color-text-3)]">
                      {t('system.user.userSyncPage.intervalHelp')}
                    </div>
                  </div>
                );
              }

              return null;
            }}
          </Form.Item>
        </div>
      </Form>
    </OperateModal>
  );
};

export default UserSyncStrategyModal;
