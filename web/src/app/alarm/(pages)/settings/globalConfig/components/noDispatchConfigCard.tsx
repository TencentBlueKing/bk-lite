'use client';

import React from 'react';
import PermissionWrapper from '@/components/permission';
import { useTranslation } from '@/utils/i18n';
import { Config, NotifyOption } from '@/app/alarm/types/settings';
import {
  Typography,
  Form,
  InputNumber,
  Select,
  Checkbox,
  Button,
  Space,
  Switch,
  Spin,
} from 'antd';
import type { FormInstance } from 'antd';

interface AssigneeOption {
  label: string;
  value: string;
}

interface NoDispatchConfigCardProps {
  expanded: boolean;
  activationLoading: boolean;
  editMode: boolean;
  form: FormInstance<Config>;
  config: Config;
  assigneeOptions: AssigneeOption[];
  notifyOptions: NotifyOption[];
  channelLoading: boolean;
  updateLoading: boolean;
  onToggleActivation: (checked: boolean) => void;
  onEnterEdit: () => void;
  onCancelEdit: () => void;
  onConfirmEdit: () => void;
}

export default function NoDispatchConfigCard({
  expanded,
  activationLoading,
  editMode,
  form,
  config,
  assigneeOptions,
  notifyOptions,
  channelLoading,
  updateLoading,
  onToggleActivation,
  onEnterEdit,
  onCancelEdit,
  onConfirmEdit,
}: NoDispatchConfigCardProps) {
  const { t } = useTranslation();

  return (
    <div className="rounded-2xl border border-(--color-border-1) bg-(--color-bg-1) p-3 pb-1 sm:p-3.5 sm:pb-1.5">
      <div className="mb-2.5 flex items-center gap-3">
        <div className="flex items-center gap-2">
          <span className="inline-block h-4 w-1 rounded-full bg-[#2F6BFF]" />
          <Typography.Title level={4} style={{ margin: 0, fontSize: '15px' }}>
            {t('settings.globalConfig.title')}
          </Typography.Title>
        </div>
        <Switch
          size="small"
          checked={expanded}
          loading={activationLoading}
          onChange={onToggleActivation}
        />
      </div>
      {expanded && (
        <div className="max-w-[640px]">
          <div className="mb-2.5 pl-3 text-[12px] leading-5 text-(--color-text-3)">
            {t('settings.globalConfig.description')}
          </div>
          <Form
            form={form}
            className="compact-config-form"
            layout="vertical"
            initialValues={config}
            style={{ maxWidth: 500 }}
          >
            <Form.Item
              name="notify_every"
              label={t('settings.globalConfig.intervalLabel')}
              rules={[
                {
                  required: true,
                  message:
                    t('common.inputTip') +
                    t('settings.globalConfig.intervalLabel'),
                },
              ]}
            >
              <InputNumber
                min={1}
                addonAfter={t('settings.globalConfig.intervalMinutes')}
                disabled={!editMode}
                style={{ width: '160px' }}
              />
            </Form.Item>

            <Form.Item
              name="notify_people"
              label={t('settings.globalConfig.personnelLabel')}
              rules={[
                {
                  required: true,
                  message:
                    t('common.selectTip') +
                    t('settings.globalConfig.personnelLabel'),
                },
              ]}
            >
              <Select
                mode="multiple"
                showSearch
                allowClear
                options={assigneeOptions}
                disabled={!editMode}
                placeholder={t('settings.globalConfig.personnelPlaceholder')}
                filterOption={(input: string, option?: { label?: string }) =>
                  !!option?.label?.toLowerCase().includes(input.toLowerCase())
                }
              />
            </Form.Item>

            <Form.Item
              name="notify_channel"
              className="mb-2"
              label={t('settings.globalConfig.notificationMethodLabel')}
              rules={[
                {
                  required: true,
                  message:
                    t('common.selectTip') +
                    t('settings.globalConfig.notificationMethodLabel'),
                },
              ]}
            >
              <Checkbox.Group
                options={notifyOptions}
                disabled={!editMode || channelLoading}
              />
              {channelLoading && (
                <div className="mt-2 flex h-8 justify-center">
                  <Spin spinning={channelLoading} />
                </div>
              )}
            </Form.Item>

            <Form.Item className="mb-0 ml-3">
              <Space>
                {editMode ? (
                  <>
                    <Button
                      type="primary"
                      size="small"
                      onClick={onConfirmEdit}
                      loading={updateLoading}
                    >
                      {t('common.confirm')}
                    </Button>
                    <Button size="small" onClick={onCancelEdit}>
                      {t('common.cancel')}
                    </Button>
                  </>
                ) : (
                  <PermissionWrapper requiredPermissions={['Edit']}>
                    <Button
                      type="primary"
                      size="small"
                      className="px-2"
                      onClick={onEnterEdit}
                    >
                      {t('common.edit')}
                    </Button>
                  </PermissionWrapper>
                )}
              </Space>
            </Form.Item>
          </Form>
        </div>
      )}
    </div>
  );
}
