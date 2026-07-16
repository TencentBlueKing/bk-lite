'use client';

import React, { useEffect, useMemo, useRef, useState } from 'react';
import { Alert, Button, Card, Empty, Select, Space, Spin, Table, Tag, Tooltip, message } from 'antd';
import type { ColumnsType } from 'antd/es/table';
import { InfoCircleOutlined, LinkOutlined, PlusOutlined } from '@ant-design/icons';

import AlertDetail from './alarmDetail';
import DeclareIncident from './declareIncident';
import LevelIcon from '@/app/alarm/components/levelIcon';
import { useAlarmApi } from '@/app/alarm/api/alarms';
import { useIncidentsApi } from '@/app/alarm/api/incidents';
import { useCommon } from '@/app/alarm/context/common';
import { AlarmTableDataItem } from '@/app/alarm/types/alarms';
import { ModalRef } from '@/app/alarm/types/types';
import { RelatedAlertItem, RelatedAlertsResponse } from '@/app/alarm/types/relatedAlerts';
import { getDefaultSelectedRelatedAlertIds, getMatchedDimensionsText } from '@/app/alarm/utils/relatedAlerts';
import { useTranslation } from '@/utils/i18n';

const MATCH_REASON_COLORS: Record<string, string> = {
  关键事件: 'red',
  相同服务: 'orange',
  相同位置: 'blue',
  相同资源: 'cyan',
  相关指标: 'green',
  相关告警: 'default',
};

interface Props {
  alert: AlarmTableDataItem;
  onRefresh?: () => void;
}

const RelatedAlertsPanel = ({ alert, onRefresh }: Props) => {
  const { t } = useTranslation();
  const { getRelatedAlerts } = useAlarmApi();
  const { addAlertsToIncident } = useIncidentsApi();
  const { levelList, levelMap } = useCommon();
  const detailRef = useRef<ModalRef>(null);

  // Store API function in ref to avoid re-triggering useEffect on every render
  const getRelatedAlertsRef = useRef(getRelatedAlerts);
  getRelatedAlertsRef.current = getRelatedAlerts;

  const [loading, setLoading] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [data, setData] = useState<RelatedAlertsResponse | null>(null);
  const [selectedIds, setSelectedIds] = useState<number[]>([]);
  const [selectedCurrentIncidentId, setSelectedCurrentIncidentId] = useState<number | null>(null);
  const [showCurrentIncidentSelector, setShowCurrentIncidentSelector] = useState(false);

  useEffect(() => {
    let disposed = false;
    const run = async () => {
      if (!alert?.id) {
        setData(null);
        setSelectedIds([]);
        return;
      }
      setLoading(true);
      try {
        const response = await getRelatedAlertsRef.current(alert.id, {
          time_window: 60,
          limit: 20,
        });
        if (disposed) {
          return;
        }
        setData(response);
        setSelectedIds(getDefaultSelectedRelatedAlertIds(response.items || []));
        setSelectedCurrentIncidentId(response.current_incidents?.[0]?.id || null);
      } finally {
        if (!disposed) {
          setLoading(false);
        }
      }
    };

    run();
    return () => {
      disposed = true;
    };
  }, [alert?.id]);

  const selectedRows = useMemo(() => {
    const items = (data?.items || []).filter((item) => selectedIds.includes(item.id));
    return [
      alert,
      ...items.map((item) => ({
        ...item,
        incident_name: (item.incidents || []).map((incident) => incident.title).join(', '),
      })),
    ];
  }, [alert, data?.items, selectedIds]);

  const selectedCount = selectedIds.length;
  const currentIncidents = data?.current_incidents || [];
  const fallbackCurrentIncidentNames = alert?.incident_name
    ? String(alert.incident_name)
      .split(',')
      .map((item) => item.trim())
      .filter(Boolean)
    : [];

  const handleAddToCurrentIncident = async () => {
    if (!selectedCurrentIncidentId || selectedIds.length === 0) {
      return;
    }
    setSubmitting(true);
    try {
      await addAlertsToIncident(String(selectedCurrentIncidentId), selectedIds);
      message.success(t('alarmCommon.successOperate'));
      setShowCurrentIncidentSelector(false);
      onRefresh?.();
      await reloadData();
    } catch {
      message.error(t('alarmCommon.operateFailed'));
    } finally {
      setSubmitting(false);
    }
  };

  const renderMatchedDimensions = (item: RelatedAlertItem) => {
    return getMatchedDimensionsText(item.matched_dimensions || {});
  };

  const handleOpenDetail = (item: RelatedAlertItem) => {
    detailRef.current?.showModal({
      title: item.title,
      form: item as unknown as AlarmTableDataItem,
      type: '',
      defaultTab: 'baseInfo',
    });
  };

  const reloadData = async () => {
    const response = await getRelatedAlertsRef.current(alert.id, {
      time_window: 60,
      limit: 20,
    });
    setData(response);
    setSelectedIds(getDefaultSelectedRelatedAlertIds(response.items || []));
    setSelectedCurrentIncidentId(response.current_incidents?.[0]?.id || null);
    setShowCurrentIncidentSelector(false);
  };

  const formatIncidentNames = (
    incidents: Array<{ title: string; incident_id: string }>
  ) => {
    if (!incidents.length) {
      return '--';
    }

    const visibleNames = incidents
      .slice(0, 2)
      .map((incident) => incident.title || incident.incident_id);
    const remainingCount = incidents.length - visibleNames.length;

    return remainingCount > 0
      ? `${visibleNames.join('、')} +${remainingCount}`
      : visibleNames.join('、');
  };

  const currentIncidentDisplayText = currentIncidents.length
    ? formatIncidentNames(currentIncidents)
    : fallbackCurrentIncidentNames.length
      ? fallbackCurrentIncidentNames.length > 2
        ? `${fallbackCurrentIncidentNames.slice(0, 2).join('、')} +${fallbackCurrentIncidentNames.length - 2}`
        : fallbackCurrentIncidentNames.join('、')
      : '--';

  const columns: ColumnsType<RelatedAlertItem> = [
    {
      title: t('alarms.alarmName', '告警名称'),
      dataIndex: 'title',
      key: 'title',
      render: (text: string) => <span className="font-medium text-[var(--color-text-1)]">{text}</span>,
    },
    {
      title: t('alarms.level', '级别'),
      dataIndex: 'level',
      key: 'level',
      render: (level: string) => {
        const target = levelList.find((item) => item.level_id === Number(level));

        return (
          <Tag color={levelMap[level || ''] as string}>
            <div className="flex items-center">
              <LevelIcon icon={target?.icon || ''} className="mr-1 h-4 w-4" />
              {target?.level_display_name || '--'}
            </div>
          </Tag>
        );
      },
    },
    {
      title: t('alarms.similarity', '相似度'),
      dataIndex: 'similarity_score',
      key: 'similarity_score',
      render: (score: number) => `${score}%`,
    },
    {
      title: t('alarms.matchReason', '关联原因'),
      dataIndex: 'match_reason',
      key: 'match_reason',
      render: (reason: string, record: RelatedAlertItem) => (
        <Tooltip title={renderMatchedDimensions(record)}>
          <Tag color={MATCH_REASON_COLORS[reason] || 'default'}>{reason}</Tag>
          <InfoCircleOutlined className="text-xs text-[var(--color-text-2)] ml-1" />
        </Tooltip>
      ),
    },
    {
      title: t('common.actions', '操作'),
      key: 'actions',
      render: (_value, record) => (
        <div className="flex items-center gap-3 whitespace-nowrap">
          <Button type="link" size="small" className="px-0" onClick={() => handleOpenDetail(record)}>
            {t('common.view', '查看')}
          </Button>
        </div>
      ),
    },
  ];

  return (
    <Card title={t('alarms.relatedAlertsRecommend', '相关告警推荐')} size="small" className="h-full">
      {loading ? (
        <div className="flex min-h-[280px] items-center justify-center">
          <Spin />
        </div>
      ) : !data?.items?.length ? (
        <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description={t('alarms.noRelatedAlerts')} />
      ) : (
        <>
          <div className="space-y-5">
            <div className="grid gap-3 md:grid-cols-[180px_180px_minmax(0,1fr)]">
              <div className="rounded-xl border border-[var(--color-border)] bg-[var(--color-bg-1)] p-4 shadow-sm">
                <div className="text-[36px] font-semibold leading-none text-[var(--color-danger)]">{data.related_count}</div>
                <div className="mt-2 text-sm text-[var(--color-text-2)]">{t('alarms.clearlyRelated', '清晰相关')}</div>
              </div>
              <div className="rounded-xl border border-[var(--color-border)] bg-[var(--color-bg-1)] p-4 shadow-sm">
                <div className="text-[36px] font-semibold leading-none text-[var(--color-warning)]">{data.maybe_related_count}</div>
                <div className="mt-2 text-sm text-[var(--color-text-2)]">{t('alarms.maybeRelated', '可疑关联')}</div>
              </div>
              <div className="rounded-xl border border-[var(--color-border)] bg-[var(--color-bg-1)] p-4 shadow-sm">
                <div className="text-sm text-[var(--color-text-2)]">{t('alarms.currentIncidentLabel', '已归属事故')}</div>
                <div className="mt-2 flex items-center gap-2 text-base font-medium text-[var(--color-text-1)]">
                  <span>{currentIncidentDisplayText}</span>
                  {currentIncidentDisplayText !== '--' ? <span className="h-2 w-2 rounded-full bg-[var(--color-success)]" /> : null}
                </div>
              </div>
            </div>

            <div className="overflow-hidden rounded-xl border border-[var(--color-border)] bg-[var(--color-bg-1)] shadow-sm">
              <div className="flex flex-wrap items-center gap-3 border-b border-[var(--color-border)] bg-[var(--color-bg-2)] px-4 py-3">
                <div className="flex min-w-0 flex-1 flex-wrap items-center gap-3">
                  <div className="inline-flex items-center gap-2 rounded-md bg-[var(--color-primary-light)] px-3 py-2 text-sm font-medium text-[var(--color-primary)]">
                    <span className="inline-flex h-4 w-4 items-center justify-center rounded-sm bg-[var(--color-primary)] text-white">✓</span>
                    <span>{t('alarms.selectedRelatedAlerts', '已选择 {count} 条相关告警', { count: selectedCount })}</span>
                  </div>
                  <span className="text-sm text-[var(--color-text-2)]">
                    {t('alarms.currentIncidentText', '当前事故')}: {currentIncidentDisplayText}
                  </span>
                </div>

                <div className="flex flex-wrap items-center gap-2">
                  {currentIncidents.length ? (
                    showCurrentIncidentSelector ? (
                      <Space.Compact block={false}>
                        <Select
                          value={selectedCurrentIncidentId || undefined}
                          onChange={setSelectedCurrentIncidentId}
                          className="min-w-[240px]"
                          options={currentIncidents.map((incident) => ({
                            label: incident.title || incident.incident_id,
                            value: incident.id,
                          }))}
                        />
                        <Button
                          type="primary"
                          loading={submitting}
                          disabled={!selectedIds.length || !selectedCurrentIncidentId}
                          onClick={handleAddToCurrentIncident}
                        >
                          {t('common.confirm', '确认')}
                        </Button>
                      </Space.Compact>
                    ) : (
                      <Button
                        type="primary"
                        icon={<PlusOutlined />}
                        disabled={!selectedIds.length || !selectedCurrentIncidentId}
                        onClick={() => setShowCurrentIncidentSelector(true)}
                      >
                        {t('alarms.addToCurrentIncident', '添加到当前事故')}
                      </Button>
                    )
                  ) : null}

                  <Tooltip title={t('alarms.linkToOtherIncidentTip')}>
                    <span>
                      <DeclareIncident
                        rowData={selectedRows}
                        onSuccess={() => {
                          message.success(t('alarmCommon.successOperate'));
                          onRefresh?.();
                          reloadData();
                        }}
                      />
                    </span>
                  </Tooltip>
                </div>
              </div>

              <Table
                rowKey="id"
                dataSource={data.items}
                pagination={false}
                size="small"
                columns={columns}
                scroll={{ x: 920 }}
                rowSelection={{
                  selectedRowKeys: selectedIds,
                  onChange: (keys) => setSelectedIds(keys as number[]),
                  getCheckboxProps: (record) => ({
                    disabled: !!record.incidents?.length,
                  }),
                }}
              />
            </div>

            <Alert
              type="warning"
              showIcon
              icon={<LinkOutlined />}
              message={t('alarms.whyRelated')}
              description={
                <ul className="mb-0 list-disc space-y-1 pl-4 text-xs text-[var(--color-text-2)]">
                  <li>{t('alarms.whyRelatedService')}</li>
                  <li>{t('alarms.whyRelatedLocation')}</li>
                  <li>{t('alarms.whyRelatedResource')}</li>
                  <li>{t('alarms.whyRelatedTimeWindow')}</li>
                </ul>
              }
            />
          </div>
          <AlertDetail ref={detailRef} handleAction={onRefresh} />
        </>
      )}
    </Card>
  );
};

export default RelatedAlertsPanel;
