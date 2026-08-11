'use client';

import React, { useEffect, useMemo } from 'react';
import {
  ExclamationCircleFilled,
  InfoCircleOutlined,
  MinusOutlined,
  PlusOutlined,
} from '@ant-design/icons';
import { Button, Select, Spin, Switch, Tag, Tooltip } from 'antd';
import type {
  NoticeChannel,
  NoticeRuleDraft,
  NoticeUser,
} from '@/app/patch-manager/types';
import { formatUserName } from '@/utils/userDisplay';
import { useTranslation } from '@/utils/i18n';
import styles from './index.module.scss';

interface NotificationRuleMatrixProps {
  scheduleEnabled: boolean;
  notificationEnabled: boolean;
  rules: NoticeRuleDraft[];
  channels: NoticeChannel[];
  users: NoticeUser[];
  loading?: boolean;
  showValidationErrors?: boolean;
  onNotificationEnabledChange: (enabled: boolean) => void;
  onRulesChange: (rules: NoticeRuleDraft[]) => void;
}

let ruleSequence = 0;

export const createNoticeRuleDraft = (): NoticeRuleDraft => {
  ruleSequence += 1;
  return {
    key: `notice-rule-${Date.now()}-${ruleSequence}`,
    receivers: [],
  };
};

export const noticeRuleNeedsRecipients = (channelType?: string): boolean => (
  Boolean(channelType) && channelType !== 'nats'
);

const CHANNEL_TYPE_LABEL_KEYS: Record<string, string> = {
  email: 'patchManager.settingsPage.channelType.email',
  enterprise_wechat: 'patchManager.settingsPage.channelType.enterpriseWechatApp',
  enterprise_wechat_bot: 'patchManager.settingsPage.channelType.enterpriseWechat',
  feishu_bot: 'patchManager.settingsPage.channelType.feishu',
  dingtalk_bot: 'patchManager.settingsPage.channelType.dingtalk',
  custom_webhook: 'patchManager.settingsPage.channelType.customWebhook',
  nats: 'patchManager.settingsPage.channelType.nats',
};

const NotificationRuleMatrix: React.FC<NotificationRuleMatrixProps> = ({
  scheduleEnabled,
  notificationEnabled,
  rules,
  channels,
  users,
  loading = false,
  showValidationErrors = false,
  onNotificationEnabledChange,
  onRulesChange,
}) => {
  const { t } = useTranslation();
  const controlsDisabled = !scheduleEnabled || !notificationEnabled;
  const notificationEffective = scheduleEnabled && notificationEnabled;

  useEffect(() => {
    if (notificationEnabled && rules.length === 0) {
      onRulesChange([createNoticeRuleDraft()]);
    }
  }, [notificationEnabled, onRulesChange, rules.length]);

  const selectedChannelIds = useMemo(
    () => new Set(rules.flatMap((rule) => (
      rule.channel_id === undefined ? [] : [rule.channel_id]
    ))),
    [rules],
  );

  const updateRule = (key: string, patch: Partial<NoticeRuleDraft>) => {
    onRulesChange(rules.map((rule) => (
      rule.key === key ? { ...rule, ...patch } : rule
    )));
  };

  const removeRule = (key: string) => {
    onRulesChange(rules.filter((rule) => rule.key !== key));
  };

  const insertRuleAfter = (index: number) => {
    const nextRules = [...rules];
    nextRules.splice(index + 1, 0, createNoticeRuleDraft());
    onRulesChange(nextRules);
  };

  const availableChannelCount = channels.filter(
    (channel) => !selectedChannelIds.has(channel.id),
  ).length;
  const canAddRule = rules.length < channels.length && availableChannelCount > 0;
  const addRuleHint = canAddRule
    ? t('patchManager.settingsPage.insertNoticeRule')
    : t('patchManager.settingsPage.noMoreNoticeChannels');

  const handleNotificationEnabledChange = (enabled: boolean) => {
    if (enabled && rules.length === 0) {
      onRulesChange([createNoticeRuleDraft()]);
    }
    onNotificationEnabledChange(enabled);
  };

  return (
    <section className={styles.section} aria-labelledby="periodic-assessment-notice-title">
      <div className={styles.sectionHeader}>
        <div className={styles.sectionTitleRow}>
          <div id="periodic-assessment-notice-title" className={styles.sectionTitle}>
            {t('patchManager.settingsPage.periodicAssessmentNotice')}
          </div>
          <Switch
            checked={notificationEnabled}
            disabled={!scheduleEnabled}
            aria-label={t('patchManager.settingsPage.periodicAssessmentNotice')}
            onChange={handleNotificationEnabledChange}
          />
        </div>
        <div className={styles.sectionDescription}>
          <InfoCircleOutlined aria-hidden="true" />
          <span>{t('patchManager.settingsPage.periodicAssessmentNoticeHelp')}</span>
        </div>
      </div>

      {!scheduleEnabled && (
        <div className={styles.scheduleDisabledHint} role="status">
          <InfoCircleOutlined aria-hidden="true" />
          <span>{t('patchManager.settingsPage.noticeScheduleDisabled')}</span>
        </div>
      )}

      {notificationEnabled && (
        <div
          className={`${styles.matrix} ${controlsDisabled ? styles.matrixDisabled : ''}`}
          aria-disabled={controlsDisabled}
        >
          <div className={styles.matrixHeader} aria-hidden="true">
            <span>{t('patchManager.settingsPage.noticeChannel')}</span>
            <span>{t('patchManager.settingsPage.noticeChannelType')}</span>
            <span>{t('patchManager.settingsPage.noticeReceivers')}</span>
            <span>{t('patchManager.operation')}</span>
          </div>

          <Spin spinning={loading}>
            <div className={styles.matrixBody}>
              {rules.map((rule, index) => {
                const channel = channels.find((item) => item.id === rule.channel_id);
                const needsRecipients = noticeRuleNeedsRecipients(channel?.channel_type);
                const missingChannel = notificationEffective
                  && showValidationErrors
                  && !channel;
                const missingReceivers = notificationEffective
                  && showValidationErrors
                  && needsRecipients
                  && rule.receivers.length === 0;

                return (
                  <div className={styles.ruleRow} key={rule.key}>
                  <div className={styles.fieldCell}>
                    <span className={styles.mobileLabel}>
                      {t('patchManager.settingsPage.noticeChannel')}
                    </span>
                    <div className={styles.fieldControl}>
                      <Select
                        value={rule.channel_id}
                        disabled={controlsDisabled}
                        status={missingChannel ? 'error' : undefined}
                        placeholder={t('patchManager.settingsPage.selectNoticeChannel')}
                        showSearch
                        optionFilterProp="label"
                        aria-invalid={missingChannel}
                        aria-label={`${t('patchManager.settingsPage.noticeChannel')} ${index + 1}`}
                        onChange={(channelId: number) => updateRule(rule.key, {
                          channel_id: channelId,
                          receivers: [],
                        })}
                        options={channels.map((item) => ({
                          value: item.id,
                          label: item.name,
                          disabled: item.id !== rule.channel_id && selectedChannelIds.has(item.id),
                        }))}
                      />
                      {missingChannel && (
                        <Tooltip title={t('patchManager.settingsPage.noticeChannelRequired')}>
                          <ExclamationCircleFilled
                            className={styles.validationIcon}
                            aria-label={t('patchManager.settingsPage.noticeChannelRequired')}
                          />
                        </Tooltip>
                      )}
                    </div>
                  </div>

                  <div className={styles.channelTypeCell}>
                    <span className={styles.mobileLabel}>
                      {t('patchManager.settingsPage.noticeChannelType')}
                    </span>
                    {channel ? (
                      <Tag bordered={false} className={styles.channelTag}>
                        {t(CHANNEL_TYPE_LABEL_KEYS[channel.channel_type] || channel.channel_type)}
                      </Tag>
                    ) : <span className={styles.emptyValue}>—</span>}
                  </div>

                  <div className={styles.fieldCell}>
                    <span className={styles.mobileLabel}>
                      {t('patchManager.settingsPage.noticeReceivers')}
                    </span>
                    {channel?.channel_type === 'nats' ? (
                      <div className={styles.channelManagedValue}>
                        {t('patchManager.settingsPage.useChannelConfiguration')}
                      </div>
                    ) : (
                      <div className={styles.fieldControl}>
                        <Select
                          mode="multiple"
                          value={rule.receivers}
                          disabled={controlsDisabled || !channel}
                          status={missingReceivers ? 'error' : undefined}
                          placeholder={channel
                            ? t('patchManager.settingsPage.selectNoticeReceivers')
                            : t('patchManager.settingsPage.selectChannelFirst')}
                          maxTagCount="responsive"
                          showSearch
                          virtual
                          optionFilterProp="label"
                          aria-invalid={missingReceivers}
                          aria-label={`${t('patchManager.settingsPage.noticeReceivers')} ${index + 1}`}
                          onChange={(receivers: number[]) => updateRule(rule.key, { receivers })}
                          options={users.map((user) => ({
                            value: user.id,
                            label: formatUserName(user),
                          }))}
                        />
                        {missingReceivers && (
                          <Tooltip title={t('patchManager.settingsPage.noticeReceiversRequired')}>
                            <ExclamationCircleFilled
                              className={styles.validationIcon}
                              aria-label={t('patchManager.settingsPage.noticeReceiversRequired')}
                            />
                          </Tooltip>
                        )}
                      </div>
                    )}
                  </div>

                  <div className={styles.actionCell}>
                    <span className={styles.mobileLabel}>{t('patchManager.operation')}</span>
                    <div className={styles.actionButtons}>
                      <Tooltip title={addRuleHint}>
                        <Button
                          type="text"
                          size="small"
                          icon={<PlusOutlined aria-hidden="true" />}
                          disabled={controlsDisabled || !canAddRule}
                          aria-label={`${addRuleHint} ${index + 1}`}
                          onClick={() => insertRuleAfter(index)}
                        />
                      </Tooltip>
                      <Tooltip title={index === 0
                        ? t('patchManager.settingsPage.firstNoticeRuleRequired')
                        : t('patchManager.settingsPage.deleteNoticeRule')}
                      >
                        <span className={styles.actionTooltipTarget}>
                          <Button
                            type="text"
                            size="small"
                            danger={index > 0}
                            icon={<MinusOutlined aria-hidden="true" />}
                            disabled={controlsDisabled || index === 0}
                            aria-label={`${t('patchManager.settingsPage.deleteNoticeRule')} ${index + 1}`}
                            onClick={() => removeRule(rule.key)}
                          />
                        </span>
                      </Tooltip>
                    </div>
                  </div>
                  </div>
                );
              })}
            </div>
          </Spin>
        </div>
      )}
    </section>
  );
};

export default NotificationRuleMatrix;
