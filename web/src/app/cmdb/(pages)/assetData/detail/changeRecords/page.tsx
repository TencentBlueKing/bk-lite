'use client';

import React, { useState, useEffect, useMemo, useCallback, useRef } from 'react';
import { useSearchParams } from 'next/navigation';
import { DatePicker, Spin, Empty, Input, Select, Button, message } from 'antd';
import {
  SearchOutlined,
  DownloadOutlined,
  LeftOutlined,
  RightOutlined,
  CloseOutlined,
  InfoCircleOutlined,
} from '@ant-design/icons';
import dayjs from 'dayjs';
import { useTranslation } from '@/utils/i18n';
import { useCommon } from '@/app/cmdb/context/common';
import {
  useChangeRecordApi,
  useModelApi,
  useInstanceApi,
} from '@/app/cmdb/api';
import styles from './index.module.scss';
import {
  AttrFieldType,
  UserItem,
} from '@/app/cmdb/types/assetManage';

const { RangePicker } = DatePicker;

interface ChangeRecord {
  id: number;
  inst_id: number;
  model_id: string;
  label: string;
  type: string;
  scenario: string;
  operator: string;
  created_at: string;
  model_object?: string;
  message?: string;
  before_data?: any;
  after_data?: any;
}

// 场景颜色（与设计稿一致）
const SCENARIO_COLORS: Record<
  string,
  { dot: string; bg: string; text: string }
> = {
  ordinary_attribute_change: {
    dot: '#155AEF',
    bg: '#e1edfc',
    text: '#155AEF',
  },
  relation_change: { dot: '#F04438', bg: '#FEE4E2', text: '#D92D20' },
  device_lifecycle: { dot: '#12B76A', bg: '#D1FADF', text: '#039855' },
  collect_automation_change: {
    dot: '#F79009',
    bg: '#FEF0C7',
    text: '#DC6803',
  },
  model_management_change: { dot: '#7A5AF8', bg: '#EBE9FE', text: '#6938EF' },
  custom_reporting_change: { dot: '#06AED4', bg: '#CFF9FE', text: '#0E7090' },
};

// 实例历史默认展示的高信号场景
const DEFAULT_SCENARIOS = [
  'device_lifecycle',
  'relation_change',
  'ordinary_attribute_change',
];

// 统计卡片 / 筛选 chip 顺序
const STAT_KEYS = [
  'device_lifecycle',
  'relation_change',
  'ordinary_attribute_change',
  'collect_automation_change',
  'custom_reporting_change',
];

interface ScenarioTagProps {
  scenario: string;
  label: string;
}

const ScenarioTag: React.FC<ScenarioTagProps> = ({ scenario, label }) => {
  const c =
    SCENARIO_COLORS[scenario] || SCENARIO_COLORS.ordinary_attribute_change;
  return (
    <span
      className={styles.scenarioTag}
      style={{ background: c.bg, color: c.text }}
    >
      {label}
    </span>
  );
};

const ChangeRecords: React.FC = () => {
  const { t } = useTranslation();
  const changeRecordApi = useChangeRecordApi();
  const modelApi = useModelApi();
  const instanceApi = useInstanceApi();
  const commonContext = useCommon();
  const userList: UserItem[] = commonContext?.userList || [];
  const modelList = commonContext?.modelList || [];

  const searchParams = useSearchParams();
  const modelId: string = searchParams.get('model_id') || '';
  const instId: string = searchParams.get('inst_id') || '';

  const [loading, setLoading] = useState(false);
  const [exporting, setExporting] = useState(false);
  const [records, setRecords] = useState<ChangeRecord[]>([]);
  const [typeEnum, setTypeEnum] = useState<Record<string, string>>({});
  const [scenarioEnum, setScenarioEnum] = useState<Record<string, string>>({});
  const [attrList, setAttrList] = useState<AttrFieldType[]>([]);
  const [currentInstance, setCurrentInstance] = useState<Record<string, any>>(
    {}
  );

  const [scenarioFilters, setScenarioFilters] = useState<string[]>(
    DEFAULT_SCENARIOS
  );
  const [searchText, setSearchText] = useState('');
  const [dateRange, setDateRange] = useState<[string, string] | null>(null);
  const [operatorFilter, setOperatorFilter] = useState<string | undefined>(
    undefined
  );
  const [activeMonth, setActiveMonth] = useState<string | null>(null);
  const [selectedId, setSelectedId] = useState<number | null>(null);
  const [detailCollapsed, setDetailCollapsed] = useState(false);
  const [activeTab, setActiveTab] = useState<
    'summary' | 'attr_diff' | 'relation_diff'
  >('summary');
  const [expandedMonths, setExpandedMonths] = useState<Record<string, boolean>>(
    {}
  );

  // 月份分组容器 ref，用于点击月份 tab 时滚动到对应位置
  const monthRefs = useRef<Record<string, HTMLDivElement | null>>({});
  const timelineListRef = useRef<HTMLDivElement | null>(null);

  const handleMonthClick = useCallback((month: string) => {
    setActiveMonth(month);
    const el = monthRefs.current[month];
    const container = timelineListRef.current;
    if (el && container) {
      // 用容器内偏移定位，避免触发整页滚动
      const top = el.offsetTop - container.offsetTop;
      container.scrollTo({ top, behavior: 'smooth' });
    }
  }, []);

  const fetchRecords = useCallback(
    async (params: any = {}) => {
      setLoading(true);
      try {
        const query: any = {
          model_id: modelId,
          inst_id: instId,
          ...params,
        };
        const data = await changeRecordApi.getChangeRecords(query);
        const list: ChangeRecord[] = Array.isArray(data) ? data : data?.items || [];
        setRecords(list);
        if (list.length && !selectedId) {
          setSelectedId(list[0].id);
        }
      } finally {
        setLoading(false);
      }
    },
    [modelId, instId, changeRecordApi, selectedId]
  );

  useEffect(() => {
    (async () => {
      try {
        const [typeData, scenarioData, attrs, inst] = await Promise.all([
          changeRecordApi.getChangeRecordEnumData(),
          changeRecordApi.getChangeRecordScenarioEnum(),
          modelApi.getModelAttrList(modelId),
          instId ? instanceApi.getInstanceDetail(instId) : Promise.resolve({}),
        ]);
        setTypeEnum(typeData || {});
        setScenarioEnum(scenarioData || {});
        setAttrList(attrs || []);
        setCurrentInstance(inst || {});
      } catch {
        // ignore — 各项失败不阻塞主列表加载
      }
      fetchRecords();
    })();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // 属性 id → 中文名
  const attrFieldMap = useMemo(() => {
    const m: Record<string, string> = {};
    (attrList || []).forEach((a: any) => {
      m[a.attr_id] = a.attr_name || a.attr_id;
    });
    return m;
  }, [attrList]);

  // 操作者下拉选项
  const operatorOptions = useMemo(() => {
    const set = new Set<string>();
    records.forEach((r) => r.operator && set.add(r.operator));
    return Array.from(set).map((op) => ({ value: op, label: op }));
  }, [records]);

  // 应用筛选
  const filtered = useMemo(() => {
    let list = records;
    if (scenarioFilters.length > 0) {
      list = list.filter((r) => scenarioFilters.includes(r.scenario));
    }
    if (searchText) {
      list = list.filter(
        (r) =>
          (r.message || '').includes(searchText) ||
          (r.operator || '').includes(searchText)
      );
    }
    if (operatorFilter) {
      list = list.filter((r) => r.operator === operatorFilter);
    }
    if (dateRange && (dateRange[0] || dateRange[1])) {
      list = list.filter((r) => {
        const ts = dayjs(r.created_at);
        if (dateRange[0] && ts.isBefore(dayjs(dateRange[0]))) return false;
        if (dateRange[1] && ts.isAfter(dayjs(dateRange[1]))) return false;
        return true;
      });
    }
    return list;
  }, [records, scenarioFilters, searchText, operatorFilter, dateRange]);

  // 按月分组
  const grouped = useMemo(() => {
    const m: Record<string, ChangeRecord[]> = {};
    filtered.forEach((r) => {
      const month = (r.created_at || '').slice(0, 7);
      if (!m[month]) m[month] = [];
      m[month].push(r);
    });
    return Object.entries(m)
      .sort((a, b) => b[0].localeCompare(a[0]))
      .map(([month, list]) => ({
        month,
        list: list.sort(
          (a, b) =>
            new Date(b.created_at).getTime() - new Date(a.created_at).getTime()
        ),
        count: list.length,
      }));
  }, [filtered]);

  useEffect(() => {
    if (grouped.length && !activeMonth) {
      setActiveMonth(grouped[0].month);
    }
  }, [grouped, activeMonth]);

  // 统计卡片计数（基于全量 records，不受筛选影响）
  const stats = useMemo(() => {
    const m: Record<string, number> = { all: records.length };
    STAT_KEYS.forEach((k) => (m[k] = 0));
    records.forEach((r) => {
      if (m[r.scenario] !== undefined) m[r.scenario]++;
    });
    return m;
  }, [records]);

  // 详情收起时 selectedRecord 必须保持 null，否则右侧不会真正消失
  const selectedRecord = useMemo(
    () => (detailCollapsed ? null : filtered.find((r) => r.id === selectedId) || null),
    [filtered, selectedId, detailCollapsed]
  );

  // 仅在"非主动收起"且当前选中被筛掉时，兜底选第一条
  useEffect(() => {
    if (detailCollapsed) return;
    if (filtered.length && !filtered.find((r) => r.id === selectedId)) {
      setSelectedId(filtered[0].id);
    }
  }, [filtered, selectedId, detailCollapsed]);

  const toggleScenario = useCallback((key: string) => {
    if (key === 'all') {
      setScenarioFilters([]);
      return;
    }
    setScenarioFilters((prev) =>
      prev.includes(key) ? prev.filter((k) => k !== key) : [...prev, key]
    );
  }, []);

  const removeScenario = useCallback((key: string) => {
    setScenarioFilters((prev) => prev.filter((k) => k !== key));
  }, []);

  const handleExport = async () => {
    try {
      setExporting(true);
      const params: any = { model_id: modelId, inst_id: instId };
      if (scenarioFilters.length) {
        params.scenarios = scenarioFilters.join(',');
      }
      if (dateRange && dateRange[0]) params.created_at_after = dateRange[0];
      if (dateRange && dateRange[1]) params.created_at_before = dateRange[1];
      if (operatorFilter) params.operator = operatorFilter;
      if (searchText) params.message = searchText;
      const blob = await changeRecordApi.exportChangeRecords(params);
      const url = window.URL.createObjectURL(blob);
      const link = document.createElement('a');
      link.href = url;
      link.download = `change_record_${instId}_${dayjs().format(
        'YYYYMMDD_HHmmss'
      )}.xlsx`;
      document.body.appendChild(link);
      link.click();
      document.body.removeChild(link);
      window.URL.revokeObjectURL(url);
      message.success(t('OperationLog.exportSuccess'));
    } catch {
      message.error(t('OperationLog.exportFailed'));
    } finally {
      setExporting(false);
    }
  };

  const scenarioLabel = (key: string) =>
    scenarioEnum[key] ||
    t(`OperationLog.scenarioOpts.${key}`) ||
    key;

  const typeLabel = (key: string) =>
    typeEnum[key] || t(`OperationLog.operationOpts.${key}`) || key;

  const showModelName = (id: string) =>
    modelList.find((m: any) => m.model_id === id)?.model_name || id;

  // 构建 diff 行
  const diffRows = useMemo(() => {
    if (!selectedRecord || selectedRecord.label !== 'instance') return [];
    const bd = selectedRecord.before_data || {};
    const ad = selectedRecord.after_data || {};
    const keys = Array.from(
      new Set([...Object.keys(ad || {}), ...Object.keys(bd || {})])
    ).filter((k) => !k.startsWith('_'));
    return keys.map((k) => {
      const beforeStr = bd[k] !== undefined ? String(bd[k]) : '--';
      const afterStr = ad[k] !== undefined ? String(ad[k]) : '--';
      const curRaw = currentInstance[k];
      const currentStr =
        curRaw !== undefined && curRaw !== null ? String(curRaw) : '--';
      return {
        attr: attrFieldMap[k] || k,
        before: beforeStr,
        after: afterStr,
        current: currentStr,
        changed: String(bd[k] ?? '') !== String(ad[k] ?? ''),
        currentDiff: currentStr !== afterStr,
      };
    });
  }, [selectedRecord, currentInstance, attrFieldMap]);

  // 关系变更信息
  const relationInfo = useMemo(() => {
    if (!selectedRecord || selectedRecord.label !== 'instance_association')
      return null;
    const data =
      selectedRecord.type === 'create_edge'
        ? selectedRecord.after_data
        : selectedRecord.before_data;
    if (!data?.edge) return null;
    return {
      kind: selectedRecord.type === 'create_edge' ? 'add' : 'remove',
      src: data.src?.inst_name || '--',
      dst: data.dst?.inst_name || '--',
      srcModel: data.edge.src_model_id,
      dstModel: data.edge.dst_model_id,
    };
  }, [selectedRecord]);

  const idxInFiltered = selectedRecord
    ? filtered.findIndex((r) => r.id === selectedRecord.id)
    : -1;
  const canPrev = idxInFiltered > 0;
  const canNext = idxInFiltered >= 0 && idxInFiltered < filtered.length - 1;

  return (
    <Spin spinning={loading}>
      <div
        className={`${styles.changeRecords} ${
          detailCollapsed ? styles.collapsed : ''
        }`}
      >
        {/* ── 左侧时间线 ── */}
        <div className={styles.timelineCol}>
          <div className={styles.pageTitle}>
            {t('Model.changeRecords')}
            <InfoCircleOutlined
              style={{ color: 'var(--color-text-4)', fontSize: 14 }}
            />
          </div>

          {/* 统计卡片（只读，不与筛选联动） */}
          <div className={styles.statsBar}>
            <div className={styles.statCell}>
              <div className={styles.statLabel}>{t('Model.changeRecord.allChanges')}</div>
              <div
                className={styles.statCount}
                style={{ color: 'var(--color-text-1)' }}
              >
                {stats.all || 0}
              </div>
            </div>
            {STAT_KEYS.map((k) => {
              const c = SCENARIO_COLORS[k];
              return (
                <div key={k} className={styles.statCell}>
                  <div className={styles.statLabel}>{scenarioLabel(k)}</div>
                  <div className={styles.statCount} style={{ color: c.dot }}>
                    {stats[k] || 0}
                  </div>
                </div>
              );
            })}
          </div>

          {/* 场景筛选 chips */}
          <div className={styles.filterChips}>
            <button
              className={`${styles.chip} ${
                scenarioFilters.length === 0 ? styles.chipActive : ''
              }`}
              onClick={() => toggleScenario('all')}
            >
              {t('Model.changeRecord.allFilter')}
            </button>
            {STAT_KEYS.map((k) => {
              const c = SCENARIO_COLORS[k];
              const isActive = scenarioFilters.includes(k);
              return (
                <button
                  key={k}
                  className={`${styles.chip} ${
                    isActive ? styles.chipActive : ''
                  }`}
                  onClick={() => toggleScenario(k)}
                >
                  <span
                    className={styles.chipDot}
                    style={{ background: c.dot }}
                  />
                  {scenarioLabel(k)}
                  {isActive && (
                    <span
                      className={styles.chipClose}
                      onClick={(e) => {
                        e.stopPropagation();
                        removeScenario(k);
                      }}
                    >
                      ✕
                    </span>
                  )}
                </button>
              );
            })}
          </div>

          {/* 搜索 + 时间 + 操作者 + 导出 */}
          <div className={styles.filterRow}>
            <Input
              size="small"
              prefix={<SearchOutlined style={{ color: '#B2BDCC' }} />}
              placeholder={t('Model.changeRecord.searchPlaceholder')}
              value={searchText}
              onChange={(e) => setSearchText(e.target.value)}
              allowClear
              style={{ flex: 1, minWidth: 140 }}
            />
            <RangePicker
              size="small"
              style={{ width: 240 }}
              onChange={(_, ds) => {
                const range: [string, string] | null =
                  ds && (ds[0] || ds[1]) ? [ds[0] || '', ds[1] || ''] : null;
                setDateRange(range);
              }}
            />
            <Select
              size="small"
              allowClear
              placeholder={t('Model.changeRecord.operatorPlaceholder')}
              style={{ width: 110 }}
              options={operatorOptions}
              value={operatorFilter}
              onChange={(v) => setOperatorFilter(v)}
            />
            <Button
              size="small"
              icon={<DownloadOutlined />}
              loading={exporting}
              onClick={handleExport}
            />
          </div>

          {/* 月份导航 + 时间线 */}
          <div className={styles.timelineBody}>
            <div className={styles.monthNav}>
              {grouped.map((g) => (
                <div
                  key={g.month}
                  className={`${styles.monthItem} ${
                    activeMonth === g.month ? styles.monthActive : ''
                  }`}
                  onClick={() => handleMonthClick(g.month)}
                >
                  <span>{g.month}</span>
                  <span className={styles.monthBadge}>{g.count}</span>
                </div>
              ))}
            </div>

            <div className={styles.timelineList} ref={timelineListRef}>
              {grouped.length === 0 && (
                <Empty
                  image={Empty.PRESENTED_IMAGE_SIMPLE}
                  style={{ marginTop: 60 }}
                />
              )}
              {grouped.map((g) => {
                const maxShow = 6;
                const expanded = expandedMonths[g.month];
                const visible = expanded ? g.list : g.list.slice(0, maxShow);
                return (
                  <div
                    key={g.month}
                    className={styles.monthGroup}
                    ref={(el) => {
                      monthRefs.current[g.month] = el;
                    }}
                  >
                    <div className={styles.monthHeading}>{g.month}</div>
                    {visible.map((r) => {
                      const c =
                        SCENARIO_COLORS[r.scenario] ||
                        SCENARIO_COLORS.ordinary_attribute_change;
                      const [d, time] = (r.created_at || '').split(' ');
                      const isSelected = selectedRecord?.id === r.id;
                      return (
                        <div
                          key={r.id}
                          className={`${styles.timelineItem} ${
                            isSelected ? styles.selected : ''
                          }`}
                          onClick={() => {
                            setSelectedId(r.id);
                            setDetailCollapsed(false);
                          }}
                        >
                          <div
                            className={styles.timelineDot}
                            style={{ background: c.dot, borderColor: c.bg }}
                          />
                          <div className={styles.timelineContent}>
                            <div className={styles.timelineMeta}>
                              <span>
                                ● {(d || '').slice(5)} {time || ''}
                              </span>
                              <ScenarioTag
                                scenario={r.scenario}
                                label={scenarioLabel(r.scenario)}
                              />
                            </div>
                            <div className={styles.timelineTitle}>
                              {r.message ||
                                `${typeLabel(r.type)}${
                                  r.model_object || showModelName(r.model_id)
                                }`}
                            </div>
                            <div className={styles.timelineOperator}>
                              {t('Model.changeRecord.operatorLabel')}：{r.operator || '--'}
                            </div>
                          </div>
                          <div
                            style={{
                              flexShrink: 0,
                              paddingTop: 16,
                              color: 'var(--color-text-4)',
                            }}
                          >
                            <RightOutlined style={{ fontSize: 12 }} />
                          </div>
                        </div>
                      );
                    })}
                    {g.list.length > maxShow && !expanded && (
                      <div
                        className={styles.expandAll}
                        onClick={() =>
                          setExpandedMonths((p) => ({ ...p, [g.month]: true }))
                        }
                      >
                        {t('Model.changeRecord.expandAll')} ({g.list.length}) ▾
                      </div>
                    )}
                  </div>
                );
              })}
            </div>
          </div>
        </div>

        {/* ── 右侧详情 ── */}
        {!detailCollapsed && (
        <div className={styles.detailCol}>
          {!selectedRecord ? (
            <div className={styles.detailEmpty}>{t('Model.changeRecord.selectTip')}</div>
          ) : (
            <>
              <div className={styles.detailHeader}>
                <div className={styles.detailHeaderRow}>
                  <div className={styles.detailHeaderLeft}>
                    <span
                      style={{
                        width: 8,
                        height: 8,
                        borderRadius: '50%',
                        background:
                          SCENARIO_COLORS[selectedRecord.scenario]?.dot ||
                          '#155AEF',
                      }}
                    />
                    <span
                      style={{
                        fontSize: 12,
                        fontWeight: 500,
                        whiteSpace: 'nowrap',
                      }}
                    >
                      {selectedRecord.created_at}
                    </span>
                    <ScenarioTag
                      scenario={selectedRecord.scenario}
                      label={scenarioLabel(selectedRecord.scenario)}
                    />
                    <span
                      style={{
                        fontSize: 12,
                        color: 'var(--color-text-3)',
                      }}
                    >
                      {selectedRecord.operator}
                    </span>
                  </div>
                  <div style={{ display: 'flex', gap: 4 }}>
                    <Button
                      size="small"
                      disabled={!canPrev}
                      icon={<LeftOutlined />}
                      onClick={() => {
                        if (canPrev) {
                          setSelectedId(filtered[idxInFiltered - 1].id);
                          setDetailCollapsed(false);
                        }
                      }}
                    />
                    <Button
                      size="small"
                      disabled={!canNext}
                      icon={<RightOutlined />}
                      onClick={() => {
                        if (canNext) {
                          setSelectedId(filtered[idxInFiltered + 1].id);
                          setDetailCollapsed(false);
                        }
                      }}
                    />
                    <Button
                      size="small"
                      icon={<CloseOutlined />}
                      onClick={() => setDetailCollapsed(true)}
                    />
                  </div>
                </div>
              </div>

              <div className={styles.detailTabs}>
                {(
                  [
                    ['summary', t('Model.changeRecord.summary')],
                    ['attr_diff', t('Model.changeRecord.attrCompare')],
                    ['relation_diff', t('Model.changeRecord.relationCompare')],
                  ] as const
                ).map(([key, label]) => (
                  <div
                    key={key}
                    className={`${styles.detailTab} ${
                      activeTab === key ? styles.tabActive : ''
                    }`}
                    onClick={() => setActiveTab(key)}
                  >
                    {label}
                  </div>
                ))}
              </div>

              <div className={styles.detailBody}>
                {activeTab === 'summary' && (
                  <>
                    <div className={styles.section}>
                      <div className={styles.sectionTitle}>
                        <span className={styles.sectionBar} />
                        {t('Model.baseInfo')}
                      </div>
                      <div className={styles.infoGrid}>
                        <span className={styles.infoLabel}>{t('Model.changeRecord.changeObject')}</span>
                        <span className={styles.infoValue}>
                          {selectedRecord.model_object ||
                            showModelName(selectedRecord.model_id)}
                          {selectedRecord.after_data?.inst_name
                            ? ` / ${selectedRecord.after_data.inst_name}`
                            : selectedRecord.before_data?.inst_name
                              ? ` / ${selectedRecord.before_data.inst_name}`
                              : ''}
                        </span>
                        <span className={styles.infoLabel}>{t('Model.changeRecord.changeType')}</span>
                        <span className={styles.infoValue}>
                          {scenarioLabel(selectedRecord.scenario)}
                        </span>
                        <span className={styles.infoLabel}>{t('Model.changeRecord.operatorLabel')}</span>
                        <span className={styles.infoValue}>
                          {selectedRecord.operator}
                        </span>
                        <span className={styles.infoLabel}>{t('Model.changeRecord.changeTime')}</span>
                        <span className={styles.infoValue}>
                          {selectedRecord.created_at}
                        </span>
                        {selectedRecord.message ? (
                          <>
                            <span className={styles.infoLabel}>{t('Model.changeRecord.message')}</span>
                            <span className={styles.infoValue}>
                              {selectedRecord.message}
                            </span>
                          </>
                        ) : null}
                      </div>
                    </div>

                    {selectedRecord.label === 'instance' &&
                      diffRows.length > 0 && (
                        <div className={styles.section}>
                          <div className={styles.sectionTitle}>
                            <span className={styles.sectionBar} />
                            {t('Model.changeRecord.changeSummary')}
                          </div>
                          <div style={{ overflowX: 'auto' }}>
                            <table className={styles.diffTable}>
                              <thead>
                                <tr>
                                  <th style={{ width: '22%' }} />
                                  <th>{t('Model.beforeTheChange')}</th>
                                  <th>{t('Model.afterTheChange')}</th>
                                  <th>{t('Model.changeRecord.current')}</th>
                                </tr>
                              </thead>
                              <tbody>
                                {diffRows.map((row, i) => (
                                  <tr key={i}>
                                    <td className={styles.attrCell}>
                                      {row.attr}
                                    </td>
                                    <td style={{ color: 'var(--color-text-1)' }}>
                                      {row.before}
                                    </td>
                                    <td>
                                      <span
                                        style={{
                                          color: row.changed
                                            ? '#12B76A'
                                            : 'var(--color-text-1)',
                                        }}
                                      >
                                        {row.after}
                                      </span>
                                    </td>
                                    <td>
                                      <span
                                        style={{
                                          color: row.currentDiff
                                            ? '#F79009'
                                            : 'var(--color-text-1)',
                                          fontWeight: row.currentDiff
                                            ? 500
                                            : 400,
                                        }}
                                      >
                                        {row.current}
                                      </span>
                                    </td>
                                  </tr>
                                ))}
                              </tbody>
                            </table>
                          </div>
                        </div>
                    )}

                    {relationInfo && (
                      <div className={styles.section}>
                        <div className={styles.sectionTitle}>
                          <span className={styles.sectionBar} />
                          {t('Model.changeRecord.relationSummary')}
                        </div>
                        <div className={styles.relationBox}>
                          <span
                            style={{
                              color:
                                relationInfo.kind === 'add'
                                  ? '#12B76A'
                                  : '#F04438',
                              fontWeight: 600,
                            }}
                          >
                            {relationInfo.kind === 'add' ? '+' : '−'}
                          </span>
                          <span style={{ fontWeight: 500 }}>
                            {relationInfo.kind === 'add'
                              ? t('Model.changeRecord.addRelation')
                              : t('Model.changeRecord.removeRelation')}
                            ：
                          </span>
                          <span style={{ color: 'var(--color-primary)' }}>
                            {relationInfo.dst}
                          </span>
                        </div>
                      </div>
                    )}
                  </>
                )}

                {activeTab === 'attr_diff' && (
                  <>
                    <div className={styles.sectionTitle}>
                      <span className={styles.sectionBar} />
                      {t('Model.changeRecord.attrCompare')}
                    </div>
                    {diffRows.length > 0 ? (
                      <div style={{ overflowX: 'auto' }}>
                        <table className={styles.diffTable}>
                          <thead>
                            <tr>
                              <th style={{ width: '22%' }}>{t('Model.attribute')}</th>
                              <th>{t('Model.beforeTheChange')}</th>
                              <th>{t('Model.afterTheChange')}</th>
                              <th>{t('Model.changeRecord.current')}</th>
                            </tr>
                          </thead>
                          <tbody>
                            {diffRows.map((row, i) => (
                              <tr key={i}>
                                <td className={styles.attrCell}>{row.attr}</td>
                                <td
                                  style={{
                                    color: row.changed
                                      ? '#F04438'
                                      : 'var(--color-text-1)',
                                    textDecoration: row.changed
                                      ? 'line-through'
                                      : 'none',
                                    opacity: row.changed ? 0.6 : 1,
                                  }}
                                >
                                  {row.before}
                                </td>
                                <td
                                  style={{
                                    color: row.changed
                                      ? '#12B76A'
                                      : 'var(--color-text-1)',
                                    fontWeight: row.changed ? 500 : 400,
                                  }}
                                >
                                  {row.after}
                                </td>
                                <td
                                  style={{
                                    color: row.currentDiff
                                      ? '#F79009'
                                      : 'var(--color-text-1)',
                                    fontWeight: row.currentDiff ? 500 : 400,
                                  }}
                                >
                                  {row.current}
                                </td>
                              </tr>
                            ))}
                          </tbody>
                        </table>
                      </div>
                    ) : (
                      <div className={styles.emptyTip}>
                        {t('Model.changeRecord.noAttrDiff')}
                      </div>
                    )}
                  </>
                )}

                {activeTab === 'relation_diff' && (
                  <>
                    <div className={styles.sectionTitle}>
                      <span className={styles.sectionBar} />
                      {t('Model.changeRecord.relationCompare')}
                    </div>
                    {relationInfo ? (
                      <div className={styles.relationBox}>
                        <div>
                          <div
                            style={{
                              display: 'flex',
                              alignItems: 'center',
                              gap: 8,
                              marginBottom: 8,
                            }}
                          >
                            <span
                              style={{
                                fontWeight: 600,
                                color:
                                  relationInfo.kind === 'add'
                                    ? '#12B76A'
                                    : '#F04438',
                              }}
                            >
                              {relationInfo.kind === 'add' ? '+' : '−'}
                            </span>
                            <span>
                              {relationInfo.kind === 'add'
                                ? t('Model.changeRecord.addRelation')
                                : t('Model.changeRecord.removeRelation')}
                            </span>
                          </div>
                          <div
                            style={{
                              marginLeft: 20,
                              color: 'var(--color-text-2)',
                            }}
                          >
                            {relationInfo.src} → {relationInfo.dst}
                          </div>
                        </div>
                      </div>
                    ) : (
                      <div className={styles.emptyTip}>
                        {t('Model.changeRecord.noRelationDiff')}
                      </div>
                    )}
                  </>
                )}
              </div>
            </>
          )}
        </div>
        )}
      </div>
    </Spin>
  );
};

export default ChangeRecords;
