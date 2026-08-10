import React, { useState } from 'react';
import type { Meta, StoryObj } from '@storybook/nextjs';
import { IntlProvider } from 'react-intl';
import { Alert, Switch } from 'antd';

import NotificationRuleMatrix from '@/app/patch-manager/components/notification-rule-matrix';
import type { NoticeRuleDraft } from '@/app/patch-manager/types';
import zhPatchManager from '@/app/patch-manager/locales/zh.json';
import settingsStyles from '@/app/patch-manager/(pages)/settings/page.module.scss';

type LocaleJson = Record<string, unknown>;

const flattenMessages = (
  source: LocaleJson,
  prefix = '',
  result: Record<string, string> = {},
): Record<string, string> => {
  Object.entries(source).forEach(([key, value]) => {
    const messageKey = prefix ? `${prefix}.${key}` : key;
    if (value && typeof value === 'object' && !Array.isArray(value)) {
      flattenMessages(value as LocaleJson, messageKey, result);
    } else {
      result[messageKey] = String(value);
    }
  });
  return result;
};

const messages = flattenMessages(zhPatchManager as LocaleJson);

function NotificationRuleMatrixPreview() {
  const [scheduleEnabled, setScheduleEnabled] = useState(true);
  const [notificationEnabled, setNotificationEnabled] = useState(true);
  const [rules, setRules] = useState<NoticeRuleDraft[]>([
    { key: 'email', channel_id: 7, receivers: [11, 12] },
    { key: 'nats', channel_id: 9, receivers: [] },
  ]);

  return (
    <IntlProvider locale="zh" messages={messages}>
      <div style={{ width: '100%', maxWidth: 1040, padding: 24, boxSizing: 'border-box', background: '#fff' }}>
        <div className={settingsStyles.assessmentAutomationControl}>
          <div className={settingsStyles.assessmentAutomationHeader}>
            <span className={settingsStyles.assessmentAutomationTitle}>启用周期评估</span>
            <Switch
              checked={scheduleEnabled}
              aria-label="启用周期评估"
              onChange={setScheduleEnabled}
            />
          </div>
          <Alert
            type="info"
            showIcon
            message="启用后系统将按周期自动评估所有主机合规状态。关闭后不会自动创建周期评估任务，手动评估不受影响。"
          />
        </div>

        {scheduleEnabled && (
          <div className={settingsStyles.assessmentAutomationPanel}>
            <NotificationRuleMatrix
              scheduleEnabled={scheduleEnabled}
              notificationEnabled={notificationEnabled}
              rules={rules}
              channels={[
                { id: 7, name: '运维邮箱', channel_type: 'email' },
                { id: 8, name: '值班群机器人', channel_type: 'enterprise_wechat_bot' },
                { id: 9, name: '自动化工作流', channel_type: 'nats' },
              ]}
              users={[
                { id: 11, username: 'alice', display_name: 'Alice' },
                { id: 12, username: 'bob', display_name: 'Bob' },
                { id: 13, username: 'charlie', display_name: 'Charlie' },
              ]}
              onNotificationEnabledChange={setNotificationEnabled}
              onRulesChange={setRules}
            />
          </div>
        )}
      </div>
    </IntlProvider>
  );
}

const meta: Meta<typeof NotificationRuleMatrixPreview> = {
  component: NotificationRuleMatrixPreview,
  title: 'Patch Manager/Periodic Assessment Notification',
  parameters: { layout: 'padded' },
};

export default meta;

type Story = StoryObj<typeof NotificationRuleMatrixPreview>;

export const Configured: Story = {};
