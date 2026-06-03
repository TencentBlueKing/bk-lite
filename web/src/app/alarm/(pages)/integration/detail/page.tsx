'use client';

import React, { useState, useEffect, FC } from 'react';
import dayjs from 'dayjs';
import SearchFilter from '@/app/alarm/components/searchFilter';
import EventTable from '@/app/alarm/components/eventTable';
import K8sGuide from '@/app/alarm/components/k8sGuide';
import SnmpTrapGuide from '@/app/alarm/components/snmpTrapGuide';
import TeamSecretsManager from '@/app/alarm/components/teamSecretsManager';
import ZabbixGuide from '@/app/alarm/components/zabbixGuide';
import CustomBreadcrumb from '@/app/alarm/components/customBreadcrumb';
import EllipsisWithTooltip from '@/components/ellipsis-with-tooltip';
import GroupTreeSelect from '@/components/group-tree-select';
import {
  CheckCircleFilled,
  CopyOutlined,
  PlusOutlined,
  ReloadOutlined,
  RightOutlined,
} from '@ant-design/icons';
import { useSearchParams } from 'next/navigation';
import { useTranslation } from '@/utils/i18n';
import { useLocalizedTime } from '@/hooks/useLocalizedTime';
import { useCommon } from '@/app/alarm/context/common';
import { useUserInfoContext } from '@/context/userInfo';
import { AlertSourceIntegrationGuide, K8sMeta, SourceItem, TeamSecretItem } from '@/app/alarm/types/integration';
import { useAlarmApi } from '@/app/alarm/api/alarms';
import { EventItem } from '@/app/alarm/types/alarms';
import { useSourceApi } from '@/app/alarm/api/integration';
import { Alert, Button, Empty, Descriptions, message, Select, Tabs, DatePicker, Spin } from 'antd';

const IntegrationDetail: FC = () => {
  const { t } = useTranslation();
  const { convertToLocalizedTime } = useLocalizedTime();
  const { levelListEvent, levelMapEvent } = useCommon();
  const searchParams = useSearchParams();
  const {
    getAlertSourcesDetail,
    getAlertSourceIntegrationGuide,
    getK8sMeta,
    downloadK8sFile,
    listTeamSecrets,
    addTeamSecret,
  } = useSourceApi();
  const { flatGroups } = useUserInfoContext();
  const { getEventList } = useAlarmApi();
  const [loading, setLoading] = useState<boolean>(false);
  const [source, setSource] = useState<SourceItem>();
  const [integrationGuide, setIntegrationGuide] = useState<AlertSourceIntegrationGuide>();
  const [k8sMeta, setK8sMeta] = useState<K8sMeta>();
  const [k8sMetaLoading, setK8sMetaLoading] = useState<boolean>(false);
  const [integrationGuideLoading, setIntegrationGuideLoading] = useState<boolean>(false);
  const [activeTab, setActiveTab] = useState<string>('event');
  const [eventList, setEventList] = useState<EventItem[]>([]);
  const [eventLoading, setEventLoading] = useState<boolean>(false);
  const [hasLoadedEvents, setHasLoadedEvents] = useState<boolean>(false);
  const [hasInitializedK8sTab, setHasInitializedK8sTab] = useState<boolean>(false);
  const [timeRange, setTimeRange] = useState<[dayjs.Dayjs, dayjs.Dayjs]>();
  const [pagination, setPagination] = useState({
    current: 1,
    pageSize: 10,
    total: 0,
  });
  const [searchCondition, setSearchCondition] = useState<{
    field: string;
    value: string;
  } | null>(null);
  const [logoLoadFailed, setLogoLoadFailed] = useState<boolean>(false);
  const [guideTeamSecrets, setGuideTeamSecrets] = useState<TeamSecretItem[]>([]);
  const [guideTeamSecretsLoading, setGuideTeamSecretsLoading] = useState<boolean>(false);
  const [selectedGuideTeamId, setSelectedGuideTeamId] = useState<string | undefined>();
  const [showInlineAddTeam, setShowInlineAddTeam] = useState<boolean>(false);
  const [inlineAddTeamId, setInlineAddTeamId] = useState<number | undefined>();
  const [inlineAddSubmitting, setInlineAddSubmitting] = useState<boolean>(false);

  const isK8sSource = source?.source_id === 'k8s';
  const isSnmpTrapSource = source?.source_id === 'snmp_trap';
  const isZabbixSource = source?.source_type === 'zabbix' || source?.source_id === 'zabbix';

  const sourceItemId = searchParams.get('sourceItemId');

  useEffect(() => {
    if (sourceItemId) {
      getSourceDetail();
    }
  }, [sourceItemId]);

  const getSourceDetail = async () => {
    setLoading(true);
    try {
      const res = await getAlertSourcesDetail(sourceItemId as string);
      if (res) {
        setSource(res);
        setLogoLoadFailed(false);
      }
    } catch (error) {
      console.error(error);
    } finally {
      setLoading(false);
    }
  };

  const getK8sGuideMeta = async () => {
    setK8sMetaLoading(true);
    try {
      const res = await getK8sMeta();
      if (res) {
        setK8sMeta(res);
      }
    } catch (error) {
      console.error(error);
    } finally {
      setK8sMetaLoading(false);
    }
  };

  const getIntegrationGuide = async (id: string) => {
    setIntegrationGuideLoading(true);
    try {
      const res = await getAlertSourceIntegrationGuide(id);
      setIntegrationGuide(res);
    } catch (error) {
      console.error(error);
      setIntegrationGuide(undefined);
    } finally {
      setIntegrationGuideLoading(false);
    }
  };

  const copySecret = (text: string = '') => {
    navigator.clipboard.writeText(text);
    message.success(t('alarmCommon.copied'));
  };

  const fetchGuideTeamSecrets = async (autoSelect = false) => {
    if (!source?.id) return;
    setGuideTeamSecretsLoading(true);
    try {
      const res = await listTeamSecrets(source.id);
      const list: TeamSecretItem[] = Array.isArray(res)
        ? res
        : (res?.team_secrets || []);
      const normalized = list.map((item) => ({
        ...item,
        team_name:
          item.team_name ||
          flatGroups.find((g) => String(g.id) === item.team_id)?.name ||
          item.team_id,
      }));
      setGuideTeamSecrets(normalized);
      if (autoSelect && normalized.length > 0 && !selectedGuideTeamId) {
        setSelectedGuideTeamId(normalized[0].team_id);
      }
    } catch (error) {
      console.error('Failed to load team secrets:', error);
    } finally {
      setGuideTeamSecretsLoading(false);
    }
  };

  const guideUsesDefaultRenderer =
    !!source && !isK8sSource && !isSnmpTrapSource && !isZabbixSource;
  const guideHasTeamSecretSupport =
    !!source && (guideUsesDefaultRenderer || isZabbixSource);

  useEffect(() => {
    if (guideHasTeamSecretSupport) {
      fetchGuideTeamSecrets(true);
    } else {
      setGuideTeamSecrets([]);
      setSelectedGuideTeamId(undefined);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [source?.id, guideHasTeamSecretSupport]);

  const selectedGuideSecret =
    guideTeamSecrets.find((item) => item.team_id === selectedGuideTeamId)?.secret;

  const renderExampleWithSelectedSecret = (raw?: string) => {
    if (!raw) return '';
    if (!selectedGuideSecret || !source?.secret) return raw;
    return raw.split(source.secret).join(selectedGuideSecret);
  };

  const handleInlineAddTeamSecret = async () => {
    if (!source?.id || !inlineAddTeamId) {
      message.warning(t('incidents.teamRequired'));
      return;
    }
    setInlineAddSubmitting(true);
    try {
      const res = await addTeamSecret(source.id, String(inlineAddTeamId));
      message.success(t('integration.teamSecretAdded'));
      setShowInlineAddTeam(false);
      setInlineAddTeamId(undefined);
      await fetchGuideTeamSecrets();
      if (res?.team_id) setSelectedGuideTeamId(res.team_id);
    } catch (error) {
      console.error('Failed to add team secret:', error);
    } finally {
      setInlineAddSubmitting(false);
    }
  };

  const fetchEventList = async () => {
    setEventLoading(true);
    try {
      const params: any = {
        source_id: source?.source_id,
        page: pagination.current,
        page_size: pagination.pageSize,
        received_at_before: timeRange?.[1]?.toISOString(),
        received_at_after: timeRange?.[0]?.toISOString(),
      };
      if (searchCondition) {
        if (isK8sSource && searchCondition.field === 'push_source_id') {
          params.push_source_id = searchCondition.value;
        } else {
          params[searchCondition.field] = searchCondition.value;
        }
      }
      const res = await getEventList(params);
      setEventList(res.items || []);
      setPagination((prev) => ({ ...prev, total: res.count }));
      setHasLoadedEvents(true);
    } finally {
      setEventLoading(false);
    }
  };

  useEffect(() => {
    if ((activeTab === 'event' || isK8sSource) && source?.source_id) {
      fetchEventList();
    }
  }, [
    activeTab,
    source,
    pagination.current,
    pagination.pageSize,
    searchCondition,
    timeRange,
  ]);

  useEffect(() => {
    if (isK8sSource && !hasInitializedK8sTab) {
      setActiveTab('guide');
      setHasInitializedK8sTab(true);
    }
  }, [isK8sSource, hasInitializedK8sTab]);

  useEffect(() => {
    if (isK8sSource && !k8sMeta && !k8sMetaLoading) {
      getK8sGuideMeta();
    }
  }, [isK8sSource, k8sMeta, k8sMetaLoading]);

  useEffect(() => {
    if (sourceItemId && isZabbixSource) {
      getIntegrationGuide(sourceItemId);
    } else if (!isZabbixSource) {
      setIntegrationGuide(undefined);
    }
  }, [sourceItemId, isZabbixSource]);

  const onFilterSearch = (condition: { field: string; value: string }) => {
    setSearchCondition(condition);
    setPagination((prev) => ({ ...prev, current: 1 }));
  };

  const eventAttrList = [
    { attr_id: 'title', attr_name: '标题', attr_type: 'str', option: [] },
    { attr_id: 'description', attr_name: '内容', attr_type: 'str', option: [] },
    ...(isK8sSource
      ? [{ attr_id: 'push_source_id', attr_name: t('integration.pushSourceId'), attr_type: 'str', option: [] }]
      : []),
  ];

  const handleK8sDownload = async (fileKey: string, fileName: string, params: any) => {
    const blob = await downloadK8sFile(fileKey, params);
    const url = window.URL.createObjectURL(blob as Blob);
    const link = document.createElement('a');
    link.href = url;
    link.download = fileName;
    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);
    window.URL.revokeObjectURL(url);
    message.success(t('common.successfullyExported'));
  };

  const formatDisplayValue = (value?: string | number | null) => {
    if (value === null || value === undefined || value === '') {
      return '--';
    }
    return value;
  };

  const hasDisplayValue = (value?: string | number | null) => value !== null && value !== undefined && value !== '';

  const formatDisplayTime = (value?: string | null) => {
    if (!value) {
      return '--';
    }
    return convertToLocalizedTime(value);
  };

  const formatBadgeLabel = (value?: string | null) => {
    if (!value) {
      return '--';
    }
    return value
      .split('_')
      .filter(Boolean)
      .map((segment) => segment.charAt(0).toUpperCase() + segment.slice(1))
      .join(' ');
  };

  const formatEventLevelLabel = (value?: string | null) => {
    const target = levelListEvent.find(
      (item) => item.level_id === Number(value)
    );

    return target?.level_display_name || formatBadgeLabel(value || 'event');
  };

  const recentEvents = eventList.slice(0, 2);

  const sidebarMetaClassName = 'text-[11px] leading-[18px] text-[var(--color-text-2)]';
  const sidebarEllipsisClassName = 'overflow-hidden text-ellipsis whitespace-nowrap';

  const k8sSummaryMetrics = [
    {
      key: 'event_count',
      label: t('integration.cumulativeEventCount'),
      value: formatDisplayValue(source?.event_count),
      helper: hasLoadedEvents ? '累计接收的 Kubernetes 事件数量。' : '事件列表加载后会持续更新该统计。',
    },
    {
      key: 'last_event_time',
      label: t('integration.lastEventTime'),
      value: formatDisplayTime(source?.last_event_time),
      helper: source?.last_event_time ? '最近一次接入事件时间。' : '当前还没有可展示的最近事件时间。',
    },
  ];

  const k8sPrecheckItems = [
    {
      key: 'network-connectivity',
      index: '1.',
      label: '网络连通性',
      status: '可访问',
    },
    {
      key: 'push-endpoint',
      index: '2.',
      label: '推送地址有效性',
      status: '有效',
    },
    {
      key: 'yaml-download',
      index: '3.',
      label: 'YAML 文件下载',
      status: '可下载',
    },
    {
      key: 'image-access',
      index: '4.',
      label: '镜像可访问',
      status: '可拉取',
    },
    {
      key: 'rbac',
      index: '5.',
      label: 'RBAC 权限（可选）',
      status: '已配置',
    },
  ];

  const K8sSummary = () => (
    <div className="rounded-[20px] border border-[var(--color-border-1)] bg-[var(--color-bg-1)] px-5 py-4">
      <div className="flex flex-col gap-4 xl:flex-row xl:items-center xl:justify-between">
        <div className="flex items-center gap-4 xl:min-w-0 xl:flex-[0.9]">
          <div className="flex h-[82px] w-[82px] shrink-0 items-center justify-center rounded-[20px] border border-[var(--color-border-1)] bg-[var(--color-fill-1)] p-2.5">
            <div className="flex h-full w-full items-center justify-center rounded-lg bg-[var(--color-primary-bg-active)]">
              {!logoLoadFailed && source?.logo ? (
                <img
                  src={source.logo}
                  alt=""
                  className="h-14 w-14 shrink-0 rounded object-contain"
                  onError={() => setLogoLoadFailed(true)}
                />
              ) : (
                <span className="text-base font-semibold text-[var(--color-primary)]">K8s</span>
              )}
            </div>
          </div>
          <div className="min-w-0 flex-1">
            <h1 className="text-[21px] font-semibold leading-[28px] text-[var(--color-text-1)]">
              {source?.name || t('integration.k8sDetailTitle')}
            </h1>
            <p className="mt-0.5 text-[13px] leading-5 text-[var(--color-text-2)] sm:text-sm">
              {source?.description || t('integration.k8sDetailDescription')}
            </p>
          </div>
        </div>
        <div className="flex-1 border-t border-[var(--color-border-1)] pt-3 xl:min-w-[520px] xl:flex-[1.1] xl:border-t-0 xl:border-l xl:pt-0 xl:pl-7">
          <div className="grid gap-0 sm:grid-cols-2">
            {k8sSummaryMetrics.map((item, index) => (
              <div
                key={item.key}
                className={[
                  'flex min-h-[88px] flex-col justify-center py-3 sm:min-h-[96px] sm:py-2',
                  index > 0 ? 'border-t border-[var(--color-border-1)] sm:border-t-0 sm:border-l' : '',
                  index === 0 ? 'sm:pr-5' : 'sm:pl-5',
                ].join(' ')}
              >
                <div className="text-[10px] font-medium uppercase tracking-[0.08em] text-[var(--color-text-3)]">
                  {item.label}
                </div>
                <div className="mt-1.5 break-words text-[22px] font-semibold leading-[28px] text-[var(--color-text-1)]">
                  {item.value}
                </div>
                <div className="mt-1 max-w-[260px] text-[12px] leading-5 text-[var(--color-text-2)]">
                  {item.helper}
                </div>
              </div>
            ))}
          </div>
        </div>
      </div>
    </div>
  );

  const K8sSidebar = () => (
    <div className="min-w-0 xl:sticky xl:top-4 xl:self-start">
      <div className="flex flex-col gap-4 xl:max-h-[calc(100vh-32px)] xl:overflow-y-auto">
        <div className="overflow-hidden rounded-[20px] border border-[var(--color-border-1)] bg-[var(--color-bg-1)]">
          <div className="border-b border-[var(--color-border-1)] bg-[color-mix(in_srgb,var(--color-primary)_3%,var(--color-bg-1))] px-5 py-4">
            <h3 className="text-[16px] font-semibold leading-6 text-[var(--color-text-1)]">
              部署前检查
            </h3>
          </div>
          <div className="px-4 py-2.5">
            <div className="divide-y divide-[var(--color-border-1)]/70">
              {k8sPrecheckItems.map((item) => (
                <div
                  key={item.key}
                  className="flex items-center justify-between gap-3 py-3 first:pt-1.5 last:pb-1.5"
                >
                  <div className="flex min-w-0 items-center gap-3">
                    <div className="flex h-7 w-7 shrink-0 items-center justify-center rounded-full border border-[color-mix(in_srgb,var(--color-success)_18%,var(--color-bg-1))] bg-[color-mix(in_srgb,var(--color-success)_10%,var(--color-bg-1))] text-[11px] font-semibold leading-none text-[var(--color-success)]">
                      {item.index}
                    </div>
                    <div className="inline-flex min-w-0 items-center gap-2">
                      <CheckCircleFilled className="text-[12px] text-[var(--color-success)]" />
                      <span className="truncate text-[13px] font-medium leading-5 text-[var(--color-text-1)]">
                        {item.label}
                      </span>
                    </div>
                  </div>
                  <span className="shrink-0 rounded-full border border-[color-mix(in_srgb,var(--color-success)_18%,var(--color-bg-1))] bg-[color-mix(in_srgb,var(--color-success)_10%,var(--color-bg-1))] px-2.5 py-1 text-[11px] font-medium leading-4 text-[var(--color-success)]">
                    {item.status}
                  </span>
                </div>
              ))}
            </div>
          </div>
        </div>

        <div className="overflow-hidden rounded-[20px] border border-[var(--color-border-1)] bg-[var(--color-bg-1)]">
          <div className="border-b border-[var(--color-border-1)] bg-[color-mix(in_srgb,var(--color-primary)_3%,var(--color-bg-1))] px-5 py-4">
            <div className="flex items-center justify-between gap-3">
              <div>
                <h3 className="text-[16px] font-semibold leading-6 text-[var(--color-text-1)]">
                  {t('integration.recentEventsPreview')}
                </h3>
              </div>
              <button
                type="button"
                className="inline-flex h-8 w-8 cursor-pointer items-center justify-center rounded-full border border-[var(--color-border-1)] bg-[var(--color-bg-1)] text-[13px] text-[var(--color-primary)] transition hover:border-[var(--color-primary)] hover:bg-[var(--color-fill-1)] disabled:cursor-not-allowed disabled:opacity-60"
                onClick={() => fetchEventList()}
                disabled={eventLoading}
                aria-label="刷新事件"
                title="刷新事件"
              >
                <ReloadOutlined className={eventLoading ? 'animate-spin' : ''} />
              </button>
            </div>
          </div>
          <div className="p-3">
            <div className="space-y-3">
              {eventLoading && !hasLoadedEvents ? (
                <div className="py-4 text-center">
                  <Spin size="small" />
                </div>
              ) : !hasLoadedEvents ? (
                <div className="rounded-[16px] border border-dashed border-[var(--color-border-3)] bg-[var(--color-bg-1)] px-4 py-3.5 text-[12px] leading-5 text-[var(--color-text-3)]">
                  {t('integration.recentEventsPending')}
                </div>
              ) : recentEvents.length ? (
                <>
                  <div className="overflow-hidden rounded-[16px] border border-[var(--color-border-1)] bg-[var(--color-bg-1)]">
                    {recentEvents.map((event) => {
                      const levelColor = levelMapEvent[event.level || ''];
                      const eventLevelStyle = levelColor
                        ? {
                          borderColor: `color-mix(in srgb, ${levelColor} 18%, white)`,
                          backgroundColor: `color-mix(in srgb, ${levelColor} 10%, white)`,
                          color: levelColor,
                        }
                        : {
                          borderColor: 'var(--color-border-1)',
                          backgroundColor: 'var(--color-fill-1)',
                          color: 'var(--color-text-2)',
                        };

                      return (
                        <div
                          key={event.id}
                          className="px-3.5 py-3 first:pt-3.5 last:pb-3.5 [&+&]:border-t [&+&]:border-[var(--color-border-1)]"
                        >
                          <div className="flex min-w-0 items-start gap-3">
                            <div className="min-w-0 flex-1">
                              <div className="flex min-w-0 items-center gap-2">
                                <span
                                  className="inline-flex items-center gap-1.5 rounded-full border px-2.5 py-1 text-[10px] font-medium leading-4"
                                  style={eventLevelStyle}
                                >
                                  <span
                                    className="h-1.5 w-1.5 shrink-0 rounded-full"
                                    style={{ backgroundColor: levelColor || 'var(--color-text-3)' }}
                                  />
                                  {formatEventLevelLabel(event.level)}
                                </span>
                                <div className="min-w-0 flex-1 text-right text-[10px] leading-4 text-[var(--color-text-3)]">
                                  <EllipsisWithTooltip
                                    text={formatDisplayTime(event.received_at)}
                                    className={sidebarEllipsisClassName}
                                  />
                                </div>
                              </div>
                              <EllipsisWithTooltip
                                text={String(formatDisplayValue(event.title))}
                                className={`mt-2 text-[13px] font-medium leading-5 text-[var(--color-text-1)] ${sidebarEllipsisClassName}`}
                              />
                              {hasDisplayValue(event.description) ? (
                                <EllipsisWithTooltip
                                  text={String(event.description)}
                                  className={`mt-1 ${sidebarMetaClassName} ${sidebarEllipsisClassName}`}
                                />
                              ) : null}
                              <div className="mt-2 flex min-w-0 items-center gap-2 text-[11px] leading-[18px] text-[var(--color-text-2)]">
                                <span
                                  className="h-1.5 w-1.5 shrink-0 rounded-full"
                                  style={{ backgroundColor: levelColor || 'var(--color-text-3)' }}
                                />
                                <EllipsisWithTooltip
                                  text={String(formatDisplayValue(event.resource_name || event.resource_type))}
                                  className={sidebarEllipsisClassName}
                                />
                              </div>
                            </div>
                            <div className="shrink-0 rounded-full border border-[var(--color-border-1)] bg-[var(--color-fill-1)] px-2.5 py-1 text-[10px] font-medium leading-4 text-[var(--color-text-2)]">
                              <EllipsisWithTooltip
                                text={String(formatDisplayValue(event.resource_type || 'Event'))}
                                className={`max-w-[86px] ${sidebarEllipsisClassName}`}
                              />
                            </div>
                          </div>
                        </div>
                      );
                    })}
                  </div>

                  <div className="border-t border-[var(--color-border-1)] pt-3">
                    <button
                      type="button"
                      className="inline-flex cursor-pointer items-center gap-1.5 text-[12px] font-medium leading-5 text-[var(--color-primary)] transition hover:opacity-80"
                      onClick={() => setActiveTab('event')}
                    >
                      {t('integration.viewAllEvents')}
                      <RightOutlined className="text-[10px]" />
                    </button>
                  </div>
                </>
              ) : (
                <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description={t('common.noData')} />
              )}
            </div>
          </div>
        </div>
      </div>
    </div>
  );

  const IntegrationHeader = () => (
    <div className="rounded-[20px] border border-[var(--color-border-1)] bg-[var(--color-bg-1)] px-5 py-4">
      <div className="flex flex-col gap-4 sm:flex-row sm:items-center">
        <div className="flex h-[82px] w-[82px] shrink-0 items-center justify-center rounded-[20px] border border-[var(--color-border-1)] bg-[var(--color-fill-1)] p-2.5">
          <div className="flex h-full w-full items-center justify-center rounded-lg bg-[var(--color-primary-bg-active)]">
            {!logoLoadFailed && source?.logo ? (
              <img
                src={source.logo}
                alt=""
                className="h-14 w-14 shrink-0 rounded object-contain"
                onError={() => setLogoLoadFailed(true)}
              />
            ) : (
              <span className="px-2 text-center text-base font-semibold leading-5 text-[var(--color-primary)]">
                {source?.name?.slice(0, 4) || '--'}
              </span>
            )}
          </div>
        </div>
        <div className="min-w-0 flex-1">
          <h1 className="text-[21px] font-semibold leading-[28px] text-[var(--color-text-1)]">
            {source?.name}
          </h1>
          <p className="mt-0.5 break-words text-[13px] leading-5 text-[var(--color-text-2)] sm:text-sm">
            {source?.description}
          </p>
        </div>
      </div>
    </div>
  );

  const renderTeamSecretSelector = (options?: { showSecretRow?: boolean; wrapperClassName?: string }) => {
    const showSecretRow = options?.showSecretRow !== false;
    const wrapperClassName = options?.wrapperClassName ?? '';
    const existingTeamIds = guideTeamSecrets.map((item) => item.team_id);
    const availableTeams = flatGroups.filter(
      (g) => !existingTeamIds.includes(String(g.id))
    );
    const hasAnySecret = guideTeamSecrets.length > 0;
    const placeholder = '<' + t('integration.selectTeamPlaceholder') + '>';

    return (
      <div className={wrapperClassName}>
        {!hasAnySecret && !guideTeamSecretsLoading ? (
          <Alert
            className="mb-3"
            type="warning"
            showIcon
            message={t('integration.noTeamSecretGuideTitle')}
            description={t('integration.noTeamSecretGuideDesc')}
          />
        ) : null}

        <div className="mb-3">
          <div className="text-[13px] text-[var(--color-text-2)] mb-2">
            {t('integration.selectTeamForReportingLabel')}
          </div>
          <Spin spinning={guideTeamSecretsLoading}>
            <div className="flex items-center gap-2 flex-wrap">
              <Select
                style={{ minWidth: 240 }}
                placeholder={t('integration.selectTeamPlaceholder')}
                value={selectedGuideTeamId}
                onChange={(val) => setSelectedGuideTeamId(val)}
                options={guideTeamSecrets.map((item) => ({
                  label: item.team_name,
                  value: item.team_id,
                }))}
                notFoundContent={t('integration.noTeamSecrets')}
              />
              {showInlineAddTeam ? (
                <>
                  <GroupTreeSelect
                    value={inlineAddTeamId ? [inlineAddTeamId] : []}
                    onChange={(val) =>
                      setInlineAddTeamId(Array.isArray(val) ? val[0] : val)
                    }
                    placeholder={t('incidents.selectTeam')}
                    multiple={false}
                    mode="ownership"
                    style={{ width: 240 }}
                  />
                  <Button
                    type="primary"
                    size="small"
                    loading={inlineAddSubmitting}
                    disabled={!inlineAddTeamId || availableTeams.length === 0}
                    onClick={handleInlineAddTeamSecret}
                  >
                    {t('common.confirm')}
                  </Button>
                  <Button
                    size="small"
                    onClick={() => {
                      setShowInlineAddTeam(false);
                      setInlineAddTeamId(undefined);
                    }}
                  >
                    {t('common.cancel')}
                  </Button>
                </>
              ) : (
                <Button
                  type="link"
                  size="small"
                  icon={<PlusOutlined />}
                  onClick={() => setShowInlineAddTeam(true)}
                >
                  {t('integration.addTeamSecretInline')}
                </Button>
              )}
              <Button
                type="link"
                size="small"
                onClick={() => setActiveTab('teamSecrets')}
              >
                {t('integration.manageTeamSecrets')}
              </Button>
            </div>
          </Spin>
        </div>

        {showSecretRow ? (
          <Descriptions bordered size="small" column={1} labelStyle={{ width: 120 }}>
            <Descriptions.Item label={t('integration.secret')}>
              {selectedGuideSecret ? (
                <>
                  <span className="font-mono">{'******************'}</span>
                  <CopyOutlined
                    className="ml-[10px] cursor-pointer hover:text-blue-500"
                    onClick={() => copySecret(selectedGuideSecret)}
                  />
                </>
              ) : (
                <span className="text-[var(--color-text-3)]">{placeholder}</span>
              )}
            </Descriptions.Item>
          </Descriptions>
        ) : null}
      </div>
    );
  };

  const renderCredentialsCard = () => {
    const placeholder = '<' + t('integration.selectTeamPlaceholder') + '>';
    const curlRendered = renderExampleWithSelectedSecret(source?.config?.examples?.CURL);
    const pythonRendered = renderExampleWithSelectedSecret(source?.config?.examples?.Python);
    const displayCurl = selectedGuideSecret ? curlRendered : (source?.config?.examples?.CURL || '');
    const displayPython = selectedGuideSecret ? pythonRendered : (source?.config?.examples?.Python || '');

    return (
      <div className="rounded-[16px] border border-[var(--color-primary-bg-active)] bg-[var(--color-bg-1)] p-4 mb-4">
        <h4 className="mb-3 font-medium pl-2 border-l-4 border-blue-400 inline-block leading-tight">
          {t('integration.credentialsAndExamples')}
        </h4>

        {renderTeamSecretSelector({ showSecretRow: false })}

        <Descriptions bordered size="small" column={1} labelStyle={{ width: 120 }}>
          <Descriptions.Item label={t('integration.secret')}>
            {selectedGuideSecret ? (
              <>
                <span className="font-mono">{'******************'}</span>
                <CopyOutlined
                  className="ml-[10px] cursor-pointer hover:text-blue-500"
                  onClick={() => copySecret(selectedGuideSecret)}
                />
              </>
            ) : (
              <span className="text-[var(--color-text-3)]">{placeholder}</span>
            )}
          </Descriptions.Item>
          <Descriptions.Item label="CURL">
            <div className="relative">
              <pre className="bg-[var(--color-bg-5)] p-2 pr-10 rounded border border-[var(--color-border-1)] text-[13px] font-mono leading-relaxed whitespace-pre-wrap break-all max-w-full">
                <code>{displayCurl}</code>
              </pre>
              <CopyOutlined
                className={`absolute top-3 right-3 ${selectedGuideSecret ? 'cursor-pointer hover:text-blue-500' : 'cursor-not-allowed text-[var(--color-text-4)]'}`}
                onClick={() => selectedGuideSecret && copySecret(displayCurl)}
              />
            </div>
          </Descriptions.Item>
          <Descriptions.Item label="Python">
            <div className="relative">
              <pre className="bg-[var(--color-bg-5)] p-2 pr-10 rounded border border-[var(--color-border-1)] text-[13px] font-mono leading-relaxed whitespace-pre-wrap break-all max-w-full">
                <code>{displayPython}</code>
              </pre>
              <CopyOutlined
                className={`absolute top-3 right-3 ${selectedGuideSecret ? 'cursor-pointer hover:text-blue-500' : 'cursor-not-allowed text-[var(--color-text-4)]'}`}
                onClick={() => selectedGuideSecret && copySecret(displayPython)}
              />
            </div>
          </Descriptions.Item>
        </Descriptions>
      </div>
    );
  };

  const renderGuideTab = () => (
    <div className="rounded-[20px] border border-[var(--color-border-1)] bg-[var(--color-fill-1)] p-4 max-h-[calc(100vh-330px)] overflow-y-auto">
      {renderCredentialsCard()}
      <h4 className="mb-2 font-medium pl-2 border-l-4 border-blue-400 inline-block leading-tight">
        {t('integration.baseInfo')}
      </h4>
      <Descriptions
        bordered
        size="small"
        column={1}
        labelStyle={{ width: 120 }}
      >
        <Descriptions.Item label="ID">{source?.source_id}</Descriptions.Item>
        <Descriptions.Item label="url">{source?.config.url}</Descriptions.Item>
        <Descriptions.Item label="method">
          {source?.config.method}
        </Descriptions.Item>
        <Descriptions.Item label="headers">
          {JSON.stringify(source?.config.headers)}
        </Descriptions.Item>
        <Descriptions.Item label="params">
          {JSON.stringify(source?.config.params)}
        </Descriptions.Item>
        <Descriptions.Item label="content_type">
          {source?.config.content_type}
        </Descriptions.Item>
        <Descriptions.Item label="description">
          {source?.description}
        </Descriptions.Item>
      </Descriptions>
      <h4 className="mt-6 mb-2 font-medium pl-2 border-l-4 border-blue-400 inline-block leading-tight">
        {t('integration.eventFieldsMapping')}
      </h4>
      <Descriptions
        bordered
        size="small"
        column={1}
        labelStyle={{ width: 120 }}
      >
        {Object.entries(source?.config?.event_fields_mapping as any).map(
          ([key, val]: any) => (
            <Descriptions.Item key={key} label={key}>
              {val}
            </Descriptions.Item>
          )
        )}
      </Descriptions>
      <h4 className="mt-6 mb-2 font-medium pl-2 border-l-4 border-blue-400 inline-block leading-tight">
        {t('integration.eventFieldsDescription')}
      </h4>
      <Descriptions
        bordered
        size="small"
        column={1}
        labelStyle={{ width: 120 }}
      >
        {Object.entries(source?.config?.event_fields_desc_mapping as any).map(
          ([key, desc]: any) => (
            <Descriptions.Item key={key} label={key}>
              {desc}
            </Descriptions.Item>
          )
        )}
      </Descriptions>
    </div>
  );

  if (!sourceItemId) {
    return <Empty description={t('common.noData')} />;
  }

  const renderEventFilters = () => (
    <div className="mb-4 flex flex-wrap items-center gap-4">
      <SearchFilter
        attrList={eventAttrList}
        onSearch={onFilterSearch}
      />
      <div>
        <span className="mr-2">{t('integration.timeRange')}</span>
        <DatePicker.RangePicker
          showTime={{ format: 'HH:mm:ss' }}
          value={timeRange}
          onChange={(vals) => {
            setTimeRange(vals as [dayjs.Dayjs, dayjs.Dayjs]);
            setPagination((prev) => ({ ...prev, current: 1 }));
          }}
        />
      </div>
    </div>
  );

  return (
    <div className="w-full flex-1">
      <CustomBreadcrumb />

      <Spin spinning={loading}>
        {!source ? (
          <div className="mt-[24vh]">
            {!loading && <Empty description={t('common.noData')} />}
          </div>
        ) : (
          <>
            {isK8sSource ? (
              <>
                {/** Guide-first layout keeps the sidebar tied to the guide tab only. */}
                <K8sSummary />
                <div className={`mt-4 grid gap-4 xl:items-start ${activeTab === 'guide' ? 'xl:grid-cols-[minmax(0,1fr)_368px]' : 'xl:grid-cols-[minmax(0,1fr)]'}`}>
                  <div className="min-w-0 rounded-[20px] border border-[var(--color-border-1)] bg-[var(--color-bg-1)] p-4 shadow-[0_8px_24px_color-mix(in_srgb,var(--color-text-1)_3%,transparent)]">
                    <Tabs activeKey={activeTab} onChange={setActiveTab} items={[
                      {
                        key: 'guide',
                        label: t('integration.guideTab'),
                        children: (
                          <K8sGuide
                            source={source}
                            meta={k8sMeta}
                            loading={k8sMetaLoading}
                            onDownload={handleK8sDownload}
                          />
                        ),
                      },
                      {
                        key: 'event',
                        label: t('integration.eventTab'),
                        children: (
                          <>
                            {renderEventFilters()}
                            <EventTable
                              dataSource={eventList}
                              loading={eventLoading}
                              pagination={pagination}
                              tableScrollY="calc(100vh - 540px)"
                              onChange={(pag) =>
                                setPagination({
                                  current: pag.current || 1,
                                  pageSize: pag.pageSize || pagination.pageSize,
                                  total: pagination.total,
                                })
                              }
                            />
                          </>
                        ),
                      },
                      {
                        key: 'teamSecrets',
                        label: t('integration.teamSecrets'),
                        children: <TeamSecretsManager sourceId={source.id} />,
                      },
                    ]} />
                  </div>
                  {activeTab === 'guide' ? (
                    <div className="min-w-0">
                      <K8sSidebar />
                    </div>
                  ) : null}
                </div>
              </>
            ) : (
              <>
                <IntegrationHeader />
                <div className="mt-4 rounded-[20px] border border-[var(--color-border-1)] bg-[var(--color-bg-1)] p-4 shadow-[0_8px_24px_color-mix(in_srgb,var(--color-text-1)_3%,transparent)]">
                  <Tabs activeKey={activeTab} onChange={setActiveTab}>
                    <Tabs.TabPane key="event" tab={t('integration.eventTab')}>
                      {renderEventFilters()}
                      <EventTable
                        dataSource={eventList}
                        loading={eventLoading}
                        pagination={pagination}
                        tableScrollY="calc(100vh - 490px)"
                        onChange={(pag) =>
                          setPagination({
                            current: pag.current || 1,
                            pageSize: pag.pageSize || pagination.pageSize,
                            total: pagination.total,
                          })
                        }
                      />
                    </Tabs.TabPane>
                    <Tabs.TabPane key="guide" tab={t('integration.guideTab')}>
                      {isSnmpTrapSource ? (
                        <SnmpTrapGuide />
                      ) : isZabbixSource ? (
                        <Spin spinning={integrationGuideLoading}>
                          <ZabbixGuide
                            guide={integrationGuide}
                            selectedTeamSecret={selectedGuideSecret}
                            credentialsSlot={renderTeamSecretSelector({ showSecretRow: true })}
                          />
                        </Spin>
                      ) : renderGuideTab()}
                    </Tabs.TabPane>
                    {isSnmpTrapSource ? null : (
                      <Tabs.TabPane key="teamSecrets" tab={t('integration.teamSecrets')}>
                        <TeamSecretsManager sourceId={source.id} />
                      </Tabs.TabPane>
                    )}
                  </Tabs>
                </div>
              </>
            )}
          </>
        )}
      </Spin>
    </div>
  );
};

export default IntegrationDetail;
