'use client';

import React, { useEffect, useMemo, useRef, useState } from 'react';
import { Button, Drawer, Empty, Tooltip, message } from 'antd';
import {
  ApartmentOutlined,
  ArrowLeftOutlined,
  ExportOutlined,
  EyeInvisibleOutlined,
  EyeOutlined,
  InfoCircleOutlined,
  RightOutlined,
  SafetyCertificateOutlined,
  UserOutlined,
} from '@ant-design/icons';
import { useTranslation } from '@/utils/i18n';
import { useClientData } from '@/context/client';
import { useLocalizedTime } from '@/hooks/useLocalizedTime';
import { useUserApi } from '@/app/system-manager/api/user';
import type { UserStatus } from '@/app/system-manager/types/user';

interface DetailCustomField {
  key: string;
  name: string;
  value?: string;
}

interface DetailDataRule {
  id: number;
  name: string;
  app: string;
}

interface DetailGroup {
  id: number;
  name: string;
  path?: string;
  is_virtual?: boolean;
  sync_source?: number | null;
  data_rules?: DetailDataRule[];
}

interface DetailRoleSource {
  kind: 'direct' | 'group';
  group_id?: number;
  group_name?: string;
}

interface DetailRole {
  id: number;
  name: string;
  app: string;
  sources: DetailRoleSource[];
}

interface UserDetailPayload {
  username?: string;
  display_name?: string;
  email?: string;
  phone?: string;
  status?: UserStatus;
  sync_source?: number | null;
  sync_source_name?: string;
  last_login?: string | null;
  temporary_pwd?: boolean;
  locale?: string;
  timezone?: string;
  employment_status?: string;
  job_title?: string;
  job_level?: string;
  employee_no?: string;
  account_expires_at?: string | null;
  password_days_until_expire?: number | null;
  api_token_count?: number;
  manager?: number | null;
  manager_username?: string;
  manager_display_name?: string;
  is_superuser?: boolean;
  custom_fields?: DetailCustomField[];
  groups?: DetailGroup[];
  effective_roles?: DetailRole[];
}

interface UserDetailDrawerProps {
  open: boolean;
  userId?: string;
  onClose: () => void;
}

const dash = '--';

const PRIMARY_CHIP =
  'rounded border border-[color-mix(in_srgb,var(--color-primary)_24%,transparent)] bg-[color-mix(in_srgb,var(--color-primary)_12%,var(--color-bg))] px-2 py-0.5 text-xs font-medium text-[var(--color-primary)]';
const NEUTRAL_CHIP = 'rounded bg-[var(--color-fill-2)] px-2 py-0.5 text-xs font-medium text-[var(--color-text-2)]';
const INHERIT_CHIP =
  'inline-block max-w-full truncate rounded border border-[var(--color-border-2)] bg-[var(--color-fill-1)] px-2 py-0.5 text-xs font-medium text-[var(--color-text-2)]';

const STATUS_TONE: Record<string, { badge: string; dot: string }> = {
  normal: {
    badge:
      'border-[color-mix(in_srgb,var(--color-success)_24%,transparent)] bg-[color-mix(in_srgb,var(--color-success)_12%,transparent)] text-[var(--color-success)]',
    dot: 'bg-[var(--color-success)]',
  },
  disabled: {
    badge: 'border-[var(--color-border-2)] bg-[var(--color-fill-2)] text-[var(--color-text-2)]',
    dot: 'bg-[var(--color-text-3)]',
  },
  locked: {
    badge:
      'border-[color-mix(in_srgb,var(--color-fail)_24%,transparent)] bg-[color-mix(in_srgb,var(--color-fail)_12%,transparent)] text-[var(--color-fail)]',
    dot: 'bg-[var(--color-fail)]',
  },
  password_expired: {
    badge:
      'border-[color-mix(in_srgb,var(--color-warning)_24%,transparent)] bg-[color-mix(in_srgb,var(--color-warning)_16%,transparent)] text-[var(--color-warning)]',
    dot: 'bg-[var(--color-warning)]',
  },
};

const UserDetailSkeleton = () => (
  <div aria-busy="true" className="flex flex-col gap-3.5">
    <div className="flex items-center gap-4 rounded-lg border border-[var(--color-border-1)] bg-[var(--color-bg)] p-5">
      <div className="h-12 w-12 animate-neutral-pulse rounded-full bg-[var(--color-fill-2)]" />
      <div className="flex flex-1 flex-col gap-2">
        <div className="h-5 w-40 animate-neutral-pulse rounded bg-[var(--color-fill-2)]" />
        <div className="h-3 w-24 animate-neutral-pulse rounded bg-[var(--color-fill-2)]" />
      </div>
    </div>
    {[0, 1, 2].map((section) => (
      <div key={section} className="rounded-lg border border-[var(--color-border-1)] bg-[var(--color-bg)] p-5">
        <div className="mb-4 h-4 w-28 animate-neutral-pulse rounded bg-[var(--color-fill-2)]" />
        <div className="grid grid-cols-2 gap-3">
          <div className="h-4 animate-neutral-pulse rounded bg-[var(--color-fill-2)]" />
          <div className="h-4 animate-neutral-pulse rounded bg-[var(--color-fill-2)]" />
        </div>
      </div>
    ))}
  </div>
);

const maskEmail = (email?: string): string => {
  if (!email) return '';
  if (email.includes('***')) return email;
  const atIndex = email.indexOf('@');
  if (atIndex <= 1) return email;
  const username = email.slice(0, atIndex);
  const domain = email.slice(atIndex);
  if (username.length <= 3) {
    return `${username.slice(0, 1)}***${domain}`;
  }
  return `${username.slice(0, 3)}***${domain}`;
};

const maskPhone = (phone?: string): string => {
  if (!phone) return '';
  if (phone.includes('*')) return phone;
  const clean = phone.replace(/\s+/g, '');
  if (clean.length < 7) return phone;
  const start = clean.slice(0, 3);
  const end = clean.slice(-4);
  return `${start}****${end}`;
};

const DetailItem: React.FC<{ label: string; children: React.ReactNode }> = ({ label, children }) => (
  <div className="flex min-w-0 items-center gap-3 text-[13px] leading-5">
    <span className="w-28 shrink-0 whitespace-nowrap text-[var(--color-text-3)]">{label}</span>
    <div className="flex min-w-0 flex-1 items-center gap-1.5 truncate text-[var(--color-text-1)]">
      {children}
    </div>
  </div>
);

const CardSection: React.FC<{
  icon: React.ReactNode;
  title: string;
  children: React.ReactNode;
}> = ({ icon, title, children }) => (
  <div className="mb-3.5 rounded-lg border border-[var(--color-border-1)] bg-[var(--color-bg)] p-5 shadow-[0_1px_3px_rgba(0,0,0,0.03)] last:mb-0">
    <div className="mb-4 flex items-center gap-2">
      <span className="text-[16px] text-[var(--color-primary)]">{icon}</span>
      <span className="text-[15px] font-semibold text-[var(--color-text-1)]">{title}</span>
    </div>
    {children}
  </div>
);

const UserDetailDrawer: React.FC<UserDetailDrawerProps> = ({ open, userId, onClose }) => {
  const { t } = useTranslation();
  const tRef = useRef(t);
  tRef.current = t;
  const { clientData } = useClientData();
  const { convertToLocalizedTime } = useLocalizedTime();
  const { getUserDetail } = useUserApi();
  const getUserDetailRef = useRef(getUserDetail);
  getUserDetailRef.current = getUserDetail;

  const [currentUserId, setCurrentUserId] = useState<string | undefined>(userId);
  const [userHistory, setUserHistory] = useState<string[]>([]);
  const [loading, setLoading] = useState(false);
  const [detail, setDetail] = useState<UserDetailPayload | null>(null);

  const [showEmail, setShowEmail] = useState(false);
  const [showPhone, setShowPhone] = useState(false);
  const [expandedGroupIds, setExpandedGroupIds] = useState<number[]>([]);

  useEffect(() => {
    if (open) {
      setCurrentUserId(userId);
      setUserHistory([]);
    }
  }, [open, userId]);

  useEffect(() => {
    if (!open || !currentUserId) return;
    let cancelled = false;
    setLoading(true);
    setDetail(null);
    setShowEmail(false);
    setShowPhone(false);

    getUserDetailRef.current({ user_id: currentUserId })
      .then((data: UserDetailPayload) => {
        if (!cancelled) {
          setDetail(data || null);
          if (data?.groups && data.groups.length > 0) {
            setExpandedGroupIds([data.groups[0].id]);
          } else {
            setExpandedGroupIds([]);
          }
        }
      })
      .catch(() => {
        if (!cancelled) {
          setDetail(null);
          message.error(tRef.current('common.fetchFailed'));
        }
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [open, currentUserId]);

  const appLabel = (app: string) => {
    if (!app) return t('system.user.detail.platform');
    return clientData.find((item) => item.name === app)?.display_name || app;
  };

  const statusView = useMemo(() => {
    const tone = STATUS_TONE[detail?.status || ''] || {
      badge: 'border-[var(--color-border-2)] bg-[var(--color-fill-2)] text-[var(--color-text-3)]',
      dot: 'bg-[var(--color-text-4)]',
    };
    const textByStatus: Record<string, string> = {
      normal: t('system.user.status.normal'),
      disabled: t('system.user.status.disabled'),
      locked: t('system.user.status.locked'),
      password_expired: t('system.user.status.password_expired'),
    };
    return {
      ...tone,
      text: textByStatus[detail?.status || ''] || dash,
    };
  }, [detail?.status, t]);

  const employmentText = (value?: string) => {
    if (value === 'employed') return t('system.user.form.employmentEmployed');
    if (value === 'resigned') return t('system.user.form.employmentResigned');
    return t('system.user.form.employmentUnspecified');
  };

  const text = (value?: string | null) => {
    const trimmed = (value || '').trim();
    return trimmed || dash;
  };

  const timeText = (value?: string | null) => (value ? convertToLocalizedTime(value) : dash);

  const passwordText = () => {
    const days = detail?.password_days_until_expire;
    if (days == null) return t('system.user.detail.passwordUnlimited');
    if (days <= 0) return t('system.user.detail.passwordExpired');
    return t('system.user.detail.passwordDaysLeft').replace('{days}', String(days));
  };

  const accountExpiryText = () => (
    detail?.account_expires_at
      ? timeText(detail.account_expires_at)
      : t('system.user.detail.accountPermanent')
  );

  const sourceText = detail?.sync_source != null
    ? (detail.sync_source_name ? `${t('system.user.detail.syncedUser')} (${detail.sync_source_name})` : t('system.user.detail.syncedUser'))
    : t('system.user.detail.localUser');

  const loginMethodText = detail?.sync_source != null
    ? t('system.user.detail.localAndSsoLogin')
    : t('system.user.detail.localLogin');

  const customFields = (detail?.custom_fields || []).filter((field) => field.name || field.key);

  const toggleGroupExpand = (groupId: number) => {
    setExpandedGroupIds((prev) =>
      prev.includes(groupId) ? prev.filter((id) => id !== groupId) : [...prev, groupId]
    );
  };

  const handleViewManager = (managerId: number) => {
    if (currentUserId) {
      setUserHistory((prev) => [...prev, currentUserId]);
    }
    setCurrentUserId(String(managerId));
  };

  const handleBack = () => {
    if (userHistory.length === 0) return;
    const prevUserId = userHistory[userHistory.length - 1];
    setUserHistory((prev) => prev.slice(0, -1));
    setCurrentUserId(prevUserId);
  };

  return (
    <Drawer
      title={
        <div className="flex items-center gap-2">
          {userHistory.length > 0 && (
            <Button
              type="text"
              size="small"
              icon={<ArrowLeftOutlined />}
              onClick={handleBack}
              aria-label={t('system.user.detail.backToPreviousUser')}
            />
          )}
          <span>{t('system.user.detail.title')}</span>
        </div>
      }
      open={open}
      width={720}
      onClose={onClose}
      classNames={{ body: 'flex flex-col bg-[var(--color-fill-1)] px-5 py-4' }}
      destroyOnHidden
    >
      {loading && !detail ? (
        <UserDetailSkeleton />
      ) : !detail ? (
        <Empty className="m-auto" />
      ) : (
        <div>
            {/* 顶部个人摘要卡片 */}
            <div className="mb-3.5 flex items-center gap-4 rounded-lg border border-[var(--color-border-1)] bg-[var(--color-bg)] p-5 shadow-[0_1px_3px_rgba(0,0,0,0.03)]">
              <div className="flex h-12 w-12 shrink-0 items-center justify-center rounded-full bg-[color-mix(in_srgb,var(--color-primary)_12%,var(--color-bg))] text-[20px] font-semibold text-[var(--color-primary)]">
                {(detail.display_name || detail.username || '?').slice(0, 1).toUpperCase()}
              </div>
              <div className="min-w-0 flex-1">
                <div className="flex items-center gap-3">
                  <span className="truncate text-[18px] font-semibold text-[var(--color-text-1)]">
                    {text(detail.display_name || detail.username)}
                  </span>
                  <span className={`inline-flex items-center gap-1.5 rounded-full border px-2.5 py-0.5 text-xs font-medium ${statusView.badge}`}>
                    <span className={`h-1.5 w-1.5 rounded-full ${statusView.dot}`} />
                    {statusView.text}
                  </span>
                </div>
                <div className="mt-1 text-xs text-[var(--color-text-3)]">
                  {sourceText}
                </div>
              </div>
            </div>

            {/* 卡片 1：账号信息 */}
            <CardSection
              icon={<UserOutlined />}
              title={t('system.user.detail.account')}
            >
              <div className="mb-3 text-[13px] font-semibold text-[var(--color-text-1)]">
                {t('system.user.detail.basic')}
              </div>
              <div className="grid grid-cols-2 gap-x-8 gap-y-3">
                <DetailItem label={t('system.user.table.username')}>
                  <span className="truncate">{text(detail.username)}</span>
                </DetailItem>
                <DetailItem label={t('system.user.table.email')}>
                  <span className="truncate">
                    {showEmail ? text(detail.email) : maskEmail(detail.email) || dash}
                  </span>
                  {detail.email && (
                    <Tooltip title={showEmail ? t('system.user.detail.hideSecret') : t('system.user.detail.showSecret')}>
                      <button
                        type="button"
                        onClick={() => setShowEmail(!showEmail)}
                        aria-label={showEmail ? t('system.user.detail.hideSecret') : t('system.user.detail.showSecret')}
                        className="inline-flex items-center text-[var(--color-text-4)] hover:text-[var(--color-primary)] cursor-pointer"
                      >
                        {showEmail ? <EyeInvisibleOutlined aria-hidden className="text-xs" /> : <EyeOutlined aria-hidden className="text-xs" />}
                      </button>
                    </Tooltip>
                  )}
                </DetailItem>

                <DetailItem label={t('system.user.table.lastName')}>
                  <span className="truncate">{text(detail.display_name)}</span>
                </DetailItem>
                <DetailItem label={t('system.user.table.phone')}>
                  <span className="truncate">
                    {showPhone ? text(detail.phone) : maskPhone(detail.phone) || dash}
                  </span>
                  {detail.phone && (
                    <Tooltip title={showPhone ? t('system.user.detail.hideSecret') : t('system.user.detail.showSecret')}>
                      <button
                        type="button"
                        onClick={() => setShowPhone(!showPhone)}
                        aria-label={showPhone ? t('system.user.detail.hideSecret') : t('system.user.detail.showSecret')}
                        className="inline-flex items-center text-[var(--color-text-4)] hover:text-[var(--color-primary)] cursor-pointer"
                      >
                        {showPhone ? <EyeInvisibleOutlined aria-hidden className="text-xs" /> : <EyeOutlined aria-hidden className="text-xs" />}
                      </button>
                    </Tooltip>
                  )}
                </DetailItem>

                <DetailItem label={t('system.user.table.status')}>
                  <span className="inline-flex items-center gap-1.5">
                    <span className={`h-1.5 w-1.5 rounded-full ${statusView.dot}`} />
                    <span>{statusView.text}</span>
                  </span>
                </DetailItem>
                <DetailItem label={t('system.user.table.lastLogin')}>
                  <span className="truncate">{timeText(detail.last_login)}</span>
                </DetailItem>

                <DetailItem label={t('system.user.detail.source')}>
                  <span className="truncate">{sourceText}</span>
                  <Tooltip title={detail.sync_source != null ? t('system.user.detail.sourceTooltip') : undefined}>
                    <InfoCircleOutlined className="text-xs text-[var(--color-text-4)]" />
                  </Tooltip>
                </DetailItem>
                <DetailItem label={t('system.user.detail.temporaryPassword')}>
                  <span>{detail.temporary_pwd ? t('common.yes') : t('common.no')}</span>
                </DetailItem>

                <DetailItem label={t('system.user.form.accountExpiresAt')}>
                  <span>{accountExpiryText()}</span>
                </DetailItem>
                <DetailItem label={t('system.user.detail.loginMethod')}>
                  <span className="truncate">{loginMethodText}</span>
                </DetailItem>

                <DetailItem label={t('system.user.detail.passwordExpiry')}>
                  <span>{passwordText()}</span>
                  <Tooltip title={t('system.user.detail.passwordTooltip')}>
                    <InfoCircleOutlined className="text-xs text-[var(--color-text-4)]" />
                  </Tooltip>
                </DetailItem>
                <DetailItem label={t('system.user.detail.apiToken')}>
                  <span>{t('system.user.detail.apiTokenEnabled', undefined, { count: detail.api_token_count ?? 0 })}</span>
                </DetailItem>
              </div>

              <div className="my-4 border-b border-dashed border-[var(--color-border-2)]" />

              <div className="mb-3 text-[13px] font-semibold text-[var(--color-text-1)]">
                {t('system.user.detail.employment')}
              </div>
              <div className="grid grid-cols-2 gap-x-8 gap-y-3">
                <DetailItem label={t('system.user.form.employmentStatus')}>
                  {detail.employment_status === 'employed' ? (
                    <span className={PRIMARY_CHIP}>
                      {employmentText(detail.employment_status)}
                    </span>
                  ) : detail.employment_status === 'resigned' ? (
                    <span className={NEUTRAL_CHIP}>
                      {employmentText(detail.employment_status)}
                    </span>
                  ) : (
                    <span className="text-[var(--color-text-3)]">{dash}</span>
                  )}
                </DetailItem>
                <DetailItem label={t('system.user.form.jobLevel')}>
                  <span className="truncate">{text(detail.job_level)}</span>
                </DetailItem>

                <DetailItem label={t('system.user.form.employeeNo')}>
                  <span className="truncate">{text(detail.employee_no)}</span>
                </DetailItem>
                <DetailItem label={t('system.user.form.manager')}>
                  {detail.manager_display_name || detail.manager_username ? (
                    <div className="flex items-center gap-1.5 min-w-0">
                      <span className="flex h-5 w-5 shrink-0 items-center justify-center rounded-full bg-[color-mix(in_srgb,var(--color-primary)_12%,var(--color-bg))] text-[11px] font-medium text-[var(--color-primary)]">
                        {(detail.manager_display_name || detail.manager_username || '?').slice(0, 1).toUpperCase()}
                      </span>
                      <span className="truncate font-medium">
                        {detail.manager_display_name || detail.manager_username}
                      </span>
                      {detail.manager && (
                        <Tooltip title={t('system.user.detail.viewManager')}>
                          <button
                            type="button"
                            aria-label={t('system.user.detail.viewManager')}
                            className="inline-flex items-center text-[var(--color-text-4)] hover:text-[var(--color-primary)] cursor-pointer"
                            onClick={() => handleViewManager(detail.manager!)}
                          >
                            <ExportOutlined aria-hidden className="text-xs" />
                          </button>
                        </Tooltip>
                      )}
                    </div>
                  ) : (
                    <span className="text-[var(--color-text-3)]">{dash}</span>
                  )}
                </DetailItem>

                <DetailItem label={t('system.user.form.jobTitle')}>
                  <span className="truncate">{text(detail.job_title)}</span>
                </DetailItem>
              </div>

              {customFields.length > 0 && (
                <>
                  <div className="my-4 border-b border-dashed border-[var(--color-border-2)]" />
                  <div className="mb-3 text-[13px] font-semibold text-[var(--color-text-1)]">
                    {t('system.user.detail.custom')}
                  </div>
                  <div className="grid grid-cols-2 gap-x-8 gap-y-3">
                    {customFields.map((field) => (
                      <DetailItem key={field.key} label={field.name || field.key}>
                        <span className="truncate">{text(field.value)}</span>
                      </DetailItem>
                    ))}
                  </div>
                </>
              )}
            </CardSection>

            {/* 卡片 2：所属组织 */}
            <CardSection
              icon={<ApartmentOutlined />}
              title={t('system.user.detail.organizations')}
            >
              {(detail.groups || []).length === 0 ? (
                <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} />
              ) : (
                <div className="space-y-2.5">
                  {(detail.groups || []).map((group) => {
                    const isExpanded = expandedGroupIds.includes(group.id);
                    return (
                      <div
                        key={group.id}
                        className="overflow-hidden rounded-md border border-[var(--color-border-1)]"
                      >
                        <button
                          type="button"
                          aria-expanded={isExpanded}
                          className="flex w-full cursor-pointer items-center justify-between border-0 bg-[var(--color-bg)] px-3.5 py-2.5 text-left transition-colors hover:bg-[var(--color-fill-1)]"
                          onClick={() => toggleGroupExpand(group.id)}
                        >
                          <div className="flex items-center gap-2 min-w-0">
                            <span className="truncate text-[13px] font-medium text-[var(--color-text-1)]">
                              {group.path || group.name}
                            </span>
                            {group.sync_source != null ? (
                              <span className={PRIMARY_CHIP}>
                                {t('system.user.detail.syncedGroup')}
                              </span>
                            ) : group.is_virtual ? (
                              <span className={NEUTRAL_CHIP}>
                                {t('system.user.detail.virtualGroup')}
                              </span>
                            ) : (
                              <span className={NEUTRAL_CHIP}>
                                {t('system.user.detail.normalGroup')}
                              </span>
                            )}
                          </div>
                          <RightOutlined
                            aria-hidden
                            className={`text-xs text-[var(--color-text-4)] transition-transform duration-200 ${
                              isExpanded ? 'rotate-90' : ''
                            }`}
                          />
                        </button>

                        {isExpanded && (
                          <div className="border-t border-[var(--color-border-1)] bg-[var(--color-fill-1)] p-3">
                            {(group.data_rules || []).length === 0 ? (
                              <div className="px-3 py-2 text-xs text-[var(--color-text-4)]">
                                {t('system.user.detail.noDataRules')}
                              </div>
                            ) : (
                              <div className="space-y-2">
                                {(group.data_rules || []).map((rule) => (
                                  <div
                                    key={rule.id}
                                    className="flex items-center justify-between gap-3 rounded-md bg-[var(--color-fill-1)]/35 px-3 py-2 text-xs"
                                  >
                                    <span className="truncate font-medium text-[var(--color-text-3)]">{appLabel(rule.app)}</span>
                                    <span className="truncate font-medium text-[var(--color-text-1)]">{rule.name}</span>
                                  </div>
                                ))}
                              </div>
                            )}
                          </div>
                        )}
                      </div>
                    );
                  })}
                </div>
              )}
            </CardSection>

            {/* 卡片 3：角色信息 */}
            <CardSection
              icon={<SafetyCertificateOutlined />}
              title={t('system.user.detail.roles')}
            >
              {detail.is_superuser ? (
                <span className={`inline-block px-2.5 py-1 ${PRIMARY_CHIP}`}>
                  {t('system.user.form.superuser')}
                </span>
              ) : (detail.effective_roles || []).length === 0 ? (
                <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} />
              ) : (
                <div className="space-y-2">
                  <div className="grid grid-cols-[1.2fr_1.2fr_1.6fr] px-3 text-xs font-medium text-[var(--color-text-3)]">
                    <span>{t('system.permission.app')}</span>
                    <span>{t('system.user.detail.roleName')}</span>
                    <span>{t('system.user.detail.roleSource')}</span>
                  </div>
                  {(detail.effective_roles || []).map((role) => (
                    <div
                      key={role.id}
                      className="grid grid-cols-[1.2fr_1.2fr_1.6fr] items-center gap-2 rounded-md bg-[var(--color-fill-1)]/35 px-3 py-2 text-[13px]"
                    >
                      <span className="truncate text-[var(--color-text-1)]">{appLabel(role.app)}</span>
                      <div>
                        <span className={PRIMARY_CHIP}>
                          {role.name}
                        </span>
                      </div>
                      <div className="flex min-w-0 flex-wrap gap-1.5">
                        {role.sources.map((source, idx) => {
                          if (source.kind === 'direct') {
                            return (
                              <span key={`direct-${idx}`} className={PRIMARY_CHIP}>
                                {t('system.user.detail.directGrant')}
                              </span>
                            );
                          }
                          const matchedGroup = source.group_id == null
                            ? undefined
                            : (detail.groups || []).find((group) => group.id === source.group_id);
                          const groupLabel = matchedGroup?.path || matchedGroup?.name || source.group_name;
                          const inheritText = groupLabel
                            ? t('system.user.detail.groupInheritFrom', 'Inherited from {group}', { group: groupLabel })
                            : t('system.user.detail.groupInherit');
                          return (
                            <span
                              key={`group-${source.group_id ?? source.group_name ?? idx}`}
                              className={INHERIT_CHIP}
                              title={inheritText}
                            >
                              {inheritText}
                            </span>
                          );
                        })}
                      </div>
                    </div>
                  ))}
                </div>
              )}
            </CardSection>
          </div>
      )}
    </Drawer>
  );
};

export default UserDetailDrawer;
