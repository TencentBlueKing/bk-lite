import React, { useMemo, useState, useEffect, useRef, useLayoutEffect } from 'react';
import { Alert, Button, Cascader, Checkbox, Spin, Tag, Tooltip } from 'antd';
import {
  CheckCircleFilled,
  CloseCircleFilled,
  ExclamationCircleFilled,
  ReloadOutlined,
  PlayCircleOutlined,
  DashboardOutlined
} from '@ant-design/icons';
import CompactEmptyState from '@/components/compact-empty-state';
import EllipsisWithTooltip from '@/components/ellipsis-with-tooltip';
import { useTranslation } from '@/utils/i18n';
import useApiClient from '@/utils/request';
import { useCommon } from '@/app/monitor/context/common';
import { parseScriptMetrics, BusinessMetricItem, cleanMeasurementName, isReservedScriptMetricId, unionVisibleDimensionNames } from './scriptMetricsParser';
import {
  applyDefaultCatalogDrafts,
  buildUnitCascaderOptions,
  catalogMetricsByName,
  extractCatalogItems,
  formatDimensionTagSummary,
  listPluginCatalogMetrics,
  mergeRetainedTrialMetricState,
  pickSelectedBusinessMetrics,
  resolveDefaultCatalogGroupId,
  CatalogMetricGroupOption,
  CatalogMetricRef,
  ScriptMetricCatalogDraft
} from './scriptMetricPersist';
import ScriptMetricGroupSelect from './scriptMetricGroupSelect';

/** checkbox | 指标 ID | 维度 | 分组 180 | 单位 150 | 采样值，列间距 12px。 */
const BUSINESS_METRIC_GRID =
  'grid grid-cols-[48px_minmax(220px,1.6fr)_minmax(160px,1fr)_180px_150px_minmax(140px,0.9fr)] items-center gap-x-3 px-3';

const BUSINESS_METRIC_TABLE_MIN_WIDTH = 'min-w-[982px]';

const INLINE_CONTROL_CLASS = 'w-full';

const DIMENSION_TAG_GAP = 4;
const DIMENSION_TAG_MAX_LINES = 2;
const DIMENSION_CHIP_CLASS =
  'inline-flex h-5 max-w-full min-w-0 items-center overflow-hidden rounded border border-[var(--color-border-1)] bg-[var(--color-fill-1)] px-1 font-mono text-[11px] leading-none text-[var(--color-text-2)]';
const DIMENSION_MORE_CLASS =
  'inline-flex h-5 shrink-0 items-center rounded border border-[var(--color-border-1)] bg-[var(--color-fill-2)] px-1 font-mono text-[11px] leading-none tabular-nums text-[var(--color-text-3)]';

/** 按真实宽度把维度标签排进两行，并为 +N 预留宽度。 */
const visibleDimensionTagCount = (
  tagWidths: number[],
  containerWidth: number,
  badgeWidth: number,
  gap = DIMENSION_TAG_GAP,
  maxLines = DIMENSION_TAG_MAX_LINES
): number => {
  if (!tagWidths.length) return 0;
  if (containerWidth <= 0) return tagWidths.length;

  const fits = (count: number, includeBadge: boolean) => {
    const widths = tagWidths
      .slice(0, count)
      .map((width) => Math.min(Math.max(width, 0), containerWidth));
    if (includeBadge) {
      widths.push(Math.min(Math.max(badgeWidth, 0), containerWidth));
    }
    let line = 1;
    let used = 0;
    for (const width of widths) {
      if (used === 0) {
        used = width;
        continue;
      }
      if (used + gap + width <= containerWidth + 0.5) {
        used += gap + width;
        continue;
      }
      line += 1;
      used = width;
      if (line > maxLines) return false;
    }
    return true;
  };

  if (fits(tagWidths.length, false)) return tagWidths.length;

  let low = 0;
  let high = tagWidths.length - 1;
  let best = 0;
  while (low <= high) {
    const mid = Math.floor((low + high) / 2);
    if (fits(mid, true)) {
      best = mid;
      low = mid + 1;
    } else {
      high = mid - 1;
    }
  }
  return best;
};

const DimensionChip: React.FC<{ label: string; measure?: boolean }> = ({
  label,
  measure = false
}) => (
  <span
    className={
      measure
        ? 'inline-flex h-5 shrink-0 items-center whitespace-nowrap rounded border border-[var(--color-border-1)] bg-[var(--color-fill-1)] px-1 font-mono text-[11px] leading-none text-[var(--color-text-2)]'
        : DIMENSION_CHIP_CLASS
    }
  >
    <span className={measure ? undefined : 'min-w-0 truncate'}>{label}</span>
  </span>
);

const DimensionTagLine: React.FC<{ names: string[] }> = ({
  names
}) => {
  const signature = names.join('\n');
  const containerRef = useRef<HTMLDivElement>(null);
  const measureRef = useRef<HTMLDivElement>(null);
  const badgeMeasureRef = useRef<HTMLSpanElement>(null);
  const [visibleCount, setVisibleCount] = useState(names.length);

  useLayoutEffect(() => {
    const container = containerRef.current;
    const measure = measureRef.current;
    if (!container || !measure) return undefined;

    const recalc = () => {
      const widths = Array.from(measure.children, (node) =>
        (node as HTMLElement).getBoundingClientRect().width
      );
      const badgeWidth = badgeMeasureRef.current?.getBoundingClientRect().width ?? 28;
      const next = visibleDimensionTagCount(
        widths,
        container.clientWidth,
        badgeWidth
      );
      setVisibleCount((prev) => (prev === next ? prev : next));
    };

    recalc();
    if (typeof ResizeObserver === 'undefined') return undefined;
    const observer = new ResizeObserver(recalc);
    observer.observe(container);
    return () => observer.disconnect();
  }, [signature]);

  if (!names.length) {
    return null;
  }

  const count = Math.min(visibleCount, names.length);
  const visible = names.slice(0, count);
  const hidden = names.slice(count);

  return (
    <div ref={containerRef} className="relative w-full min-w-0 overflow-hidden">
      <div className="flex max-h-11 min-w-0 flex-wrap content-start items-center gap-1 overflow-hidden">
        {visible.map((name) => (
          <Tooltip key={name} title={name}>
            <span className="inline-flex max-w-full min-w-0 overflow-hidden">
              <DimensionChip label={name} />
            </span>
          </Tooltip>
        ))}
        {hidden.length > 0 ? (
          <Tooltip
            title={(
              <div className="flex max-w-[280px] flex-col gap-0.5">
                {hidden.map((name) => (
                  <span key={name} className="break-all font-mono text-xs">
                    {name}
                  </span>
                ))}
              </div>
            )}
          >
            <span className={DIMENSION_MORE_CLASS}>+{hidden.length}</span>
          </Tooltip>
        ) : null}
      </div>
      <div
        ref={measureRef}
        aria-hidden
        className="pointer-events-none absolute left-0 top-0 flex w-max gap-1 opacity-0"
      >
        {names.map((name) => (
          <DimensionChip key={name} measure label={name} />
        ))}
      </div>
      <span
        ref={badgeMeasureRef}
        aria-hidden
        className={`${DIMENSION_MORE_CLASS} pointer-events-none absolute left-0 top-0 opacity-0`}
      >
        +{names.length}
      </span>
    </div>
  );
};

const SAMPLE_PREVIEW_MAX = 20;
/** 采样值 +「共 N 条」两行；无第二行时也占位，避免行高跳动。 */
const SAMPLE_VALUE_STACK_CLASS =
  'flex h-8 w-full min-w-0 cursor-default flex-col justify-center';

const SamplePreviewTable: React.FC<{
  samples: Array<{ value: number | string; tags?: Record<string, string> }>;
}> = ({ samples }) => {
  const { t } = useTranslation();
  const visible = samples.slice(0, SAMPLE_PREVIEW_MAX);
  const remaining = Math.max(0, samples.length - SAMPLE_PREVIEW_MAX);
  return (
    <table className="border-separate border-spacing-x-3 border-spacing-y-0.5 text-[11px] leading-4">
      <tbody>
        {visible.map((sample, index) => (
          <tr key={index}>
            <td className="max-w-[220px] truncate align-top font-mono">
              {formatDimensionTagSummary(sample.tags) || '—'}
            </td>
            <td className="whitespace-nowrap text-right align-top font-mono tabular-nums">
              {String(sample.value)}
            </td>
          </tr>
        ))}
        {remaining > 0 ? (
          <tr>
            <td colSpan={2} className="pt-1 text-right opacity-80">
              {t('monitor.integrations.trialRunSampleMore', '还有 {count} 条', {
                count: remaining
              })}
            </td>
          </tr>
        ) : null}
      </tbody>
    </table>
  );
};

export interface TrialRunTaskState {
  status: 'pending' | 'running' | 'success' | 'failed' | 'warning';
  warning_type?: 'no_permission' | 'rate_limit';
  fingerprint?: string;
  result?: Record<string, any>;
  error_message?: string;
  started_at?: string | null;
  finished_at?: string | null;
}

/** 与失败 Alert 同一判定：未通过则确认不可用。运行中不算失败。 */
export const scriptTrialBlocksMetricActions = (
  task?: TrialRunTaskState | null
): boolean => {
  if (!task?.status || task.status === 'pending' || task.status === 'running') {
    return false;
  }
  const parsed =
    task.result || task.error_message
      ? parseScriptMetrics(
        task.result,
        task.started_at,
        task.finished_at,
        task.error_message
      )
      : null;
  const isNonZeroExit = Boolean(task.result && task.result.exit_code !== 0);
  return (
    task.status === 'failed' ||
    task.status === 'warning' ||
    Boolean(task.warning_type) ||
    isNonZeroExit ||
    Boolean(parsed?.isTimeout) ||
    Boolean(parsed?.isNodeUnavailable)
  );
};

const TrialActionsBlockedNote: React.FC = () => {
  const { t } = useTranslation();
  return (
    <div className="text-[13px] font-medium text-[var(--color-text-1)]">
      {t(
        'monitor.integrations.trialRunActionsUnavailable',
        '调试未通过，确认不可用。'
      )}
    </div>
  );
};

interface ScriptTrialRunAreaProps {
  task?: TrialRunTaskState;
  spinning?: boolean;
  onTrialRun: () => void;
  nodeSelected?: boolean;
  instanceName?: string;
  pluginId?: string | number;
  objectId?: string | number;
  onSelectedMetricsChange?: (metrics: BusinessMetricItem[]) => void;
  onBusinessMetricsAvailableChange?: (available: boolean) => void;
  onCatalogBlockingChange?: (blocking: boolean) => void;
  onCatalogErrorChange?: (failed: boolean) => void;
}

const ScriptTrialRunArea: React.FC<ScriptTrialRunAreaProps> = ({
  task,
  spinning = false,
  onTrialRun,
  nodeSelected = true,
  instanceName,
  pluginId,
  objectId,
  onSelectedMetricsChange,
  onBusinessMetricsAvailableChange,
  onCatalogBlockingChange,
  onCatalogErrorChange
}) => {
  const { t } = useTranslation();
  const { get } = useApiClient();
  const commonContext = useCommon();
  const [selectedMetrics, setSelectedMetrics] = useState<Record<string, boolean>>({});
  const [catalogByKey, setCatalogByKey] = useState<Record<string, ScriptMetricCatalogDraft>>({});
  const [groupOptions, setGroupOptions] = useState<CatalogMetricGroupOption[]>([]);
  const [catalogMetrics, setCatalogMetrics] = useState<CatalogMetricRef[]>([]);
  const [catalogLoaded, setCatalogLoaded] = useState(false);
  const [catalogError, setCatalogError] = useState(false);
  const [catalogEpoch, setCatalogEpoch] = useState(0);
  const [trialSubmitting, setTrialSubmitting] = useState(false);
  const retainedMetricStateRef = useRef({
    selected: {} as Record<string, boolean>,
    catalog: {} as Record<string, ScriptMetricCatalogDraft>
  });
  const unitOptions = useMemo(
    () => buildUnitCascaderOptions(commonContext?.groupedUnitList || []),
    [commonContext?.groupedUnitList]
  );

  const isSpinning = spinning || task?.status === 'pending' || task?.status === 'running';
  const trialBusy = isSpinning || trialSubmitting;

  useEffect(() => {
    if (isSpinning || (task?.status && task.status !== 'pending')) {
      setTrialSubmitting(false);
    }
  }, [isSpinning, task?.status]);

  const handleTrialClick = () => {
    if (trialBusy || !nodeSelected) return;
    setTrialSubmitting(true);
    onTrialRun();
  };

  const parsedOutput = useMemo(() => {
    if (!task?.result && !task?.error_message) {
      return null;
    }
    return parseScriptMetrics(
      task.result,
      task.started_at,
      task.finished_at,
      task.error_message
    );
  }, [task]);

  // 与失败 Alert 同一判定：只有 status=success 且退出码为 0，且不是超时 / 节点不可用 / 告警，才允许确认。
  const isNonZeroExit = Boolean(task?.result && task.result.exit_code !== 0);
  const blocksMetricActions = scriptTrialBlocksMetricActions(task);
  const canFeedScriptMetricActions =
    task?.status === 'success' && !blocksMetricActions;

  const defaultGroupId = useMemo(
    () => resolveDefaultCatalogGroupId(groupOptions),
    [groupOptions]
  );
  const existingByName = useMemo(
    () => catalogMetricsByName(catalogMetrics),
    [catalogMetrics]
  );

  useEffect(() => {
    retainedMetricStateRef.current.selected = selectedMetrics;
  }, [selectedMetrics]);

  useEffect(() => {
    retainedMetricStateRef.current.catalog = catalogByKey;
  }, [catalogByKey]);

  // 重新调试成功：刷新采样值；仍存在的指标保留勾选/分组/单位/描述；消失的视为未勾选。
  // 已有目录指标的分组/单位从目录预填，不用后缀猜测。
  useEffect(() => {
    const metrics = parsedOutput?.businessMetrics;
    if (!metrics?.length) {
      if (parsedOutput) {
        retainedMetricStateRef.current = { selected: {}, catalog: {} };
        setSelectedMetrics({});
        setCatalogByKey({});
      }
      return;
    }
    if (pluginId && objectId && !catalogLoaded) {
      return;
    }
    const merged = mergeRetainedTrialMetricState({
      nextMetrics: metrics,
      prevSelected: retainedMetricStateRef.current.selected,
      prevCatalog: retainedMetricStateRef.current.catalog
    });
    const withDefaults = applyDefaultCatalogDrafts(
      metrics,
      merged.catalog,
      defaultGroupId,
      unitOptions,
      existingByName
    );
    const next = { selected: merged.selected, catalog: withDefaults.catalog };
    retainedMetricStateRef.current = next;
    setSelectedMetrics(next.selected);
    setCatalogByKey(next.catalog);
  }, [
    parsedOutput,
    defaultGroupId,
    unitOptions,
    existingByName,
    catalogLoaded,
    pluginId,
    objectId
  ]);

  useEffect(() => {
    if (!pluginId || !objectId) {
      setGroupOptions([]);
      setCatalogMetrics([]);
      setCatalogError(false);
      setCatalogLoaded(true);
      return;
    }
    let cancelled = false;
    setCatalogLoaded(false);
    setCatalogError(false);
    const loadCatalog = async () => {
      try {
        const [groupRes, metricRefs] = await Promise.all([
          get('/monitor/api/metrics_group/', {
            params: {
              monitor_object_id: objectId,
              monitor_plugin_id: pluginId,
              page: 1,
              page_size: 100
            },
            suppressErrorNotification: true
          }),
          listPluginCatalogMetrics({
            pluginId,
            objectId,
            client: { get }
          })
        ]);
        if (!cancelled) {
          setGroupOptions(extractCatalogItems<CatalogMetricGroupOption>(groupRes));
          setCatalogMetrics(metricRefs);
          setCatalogError(false);
          setCatalogLoaded(true);
        }
      } catch {
        if (!cancelled) {
          setGroupOptions([]);
          setCatalogMetrics([]);
          setCatalogError(true);
          setCatalogLoaded(false);
        }
      }
    };
    void loadCatalog();
    return () => {
      cancelled = true;
    };
  }, [get, pluginId, objectId, catalogEpoch]);

  // 仅成功调试把勾选业务指标交给确认；失败即使解析到行也不喂。
  // 目录未就绪时不喂，避免把空草稿当新建指标写入。
  const catalogBlocking = Boolean(pluginId && objectId && !catalogLoaded);

  useEffect(() => {
    onCatalogBlockingChange?.(catalogBlocking);
  }, [catalogBlocking, onCatalogBlockingChange]);

  useEffect(() => {
    onCatalogErrorChange?.(catalogError);
  }, [catalogError, onCatalogErrorChange]);

  useEffect(() => {
    return () => {
      onCatalogBlockingChange?.(false);
      onCatalogErrorChange?.(false);
    };
  }, [onCatalogBlockingChange, onCatalogErrorChange]);

  useEffect(() => {
    if (!onSelectedMetricsChange) return;
    if (
      catalogBlocking ||
      !canFeedScriptMetricActions ||
      !parsedOutput?.businessMetrics?.length
    ) {
      onSelectedMetricsChange([]);
      return;
    }
    onSelectedMetricsChange(
      pickSelectedBusinessMetrics(
        parsedOutput.businessMetrics,
        selectedMetrics,
        catalogByKey
      )
    );
  }, [
    catalogBlocking,
    canFeedScriptMetricActions,
    selectedMetrics,
    parsedOutput,
    catalogByKey,
    onSelectedMetricsChange
  ]);

  useEffect(() => {
    onBusinessMetricsAvailableChange?.(
      !catalogBlocking &&
        canFeedScriptMetricActions &&
        (parsedOutput?.businessMetrics?.length || 0) > 0
    );
  }, [
    catalogBlocking,
    canFeedScriptMetricActions,
    parsedOutput,
    onBusinessMetricsAvailableChange
  ]);

  useEffect(() => {
    return () => onBusinessMetricsAvailableChange?.(false);
  }, [onBusinessMetricsAvailableChange]);

  const updateCatalog = (key: string, patch: ScriptMetricCatalogDraft) => {
    setCatalogByKey((prev) => ({
      ...prev,
      [key]: {
        ...prev[key],
        ...patch
      }
    }));
  };

  const toggleMetric = (key: string, disabled = false) => {
    if (isSpinning || disabled) return;
    setSelectedMetrics((prev) => ({
      ...prev,
      [key]: !prev[key]
    }));
  };

  const toggleAllMetrics = (checked: boolean) => {
    if (isSpinning || !parsedOutput?.businessMetrics) return;
    const nextMap: Record<string, boolean> = {};
    parsedOutput.businessMetrics.forEach((m) => {
      nextMap[m.key] = checked && !isReservedScriptMetricId(m.name);
    });
    setSelectedMetrics(nextMap);
  };

  const retryCatalog = () => setCatalogEpoch((n) => n + 1);
  const catalogErrorAlert = catalogError ? (
    <Alert
      className="mb-3 py-1 text-[13px]"
      type="warning"
      showIcon
      message={
        <span>
          {t(
            'monitor.integrations.scriptCatalogLoadFailed',
            '指标目录加载失败，暂无法确认写入'
          )}
          <Button
            type="link"
            size="small"
            className="ml-1 h-auto px-0"
            onClick={retryCatalog}
          >
            {t('common.retry', '重试')}
          </Button>
        </span>
      }
    />
  ) : null;

  // 1. 未运行状态
  if (!task || !task.status) {
    return (
      <div className="mt-4 mb-4 rounded-lg border border-[var(--color-border-1)] bg-[var(--color-bg-1)] p-4">
        <div className="flex items-center justify-between mb-3 border-b border-[var(--color-border-1)] pb-2">
          <div className="flex items-center gap-2">
            <DashboardOutlined className="text-[var(--color-primary)] text-[15px]" />
            <b className="text-[14px] text-[var(--color-text-1)]">
              {t('monitor.integrations.trialRunAreaTitle', '调试结果')}
            </b>
            {instanceName && (
              <Tag className="ml-1 text-[12px]">{instanceName}</Tag>
            )}
          </div>
        </div>
        {catalogErrorAlert}
        <div className="flex flex-col items-center justify-center py-6 px-4 rounded-md border border-dashed border-[var(--color-border-2)] bg-[var(--color-bg-2)]">
          <CompactEmptyState
            description={t(
              'monitor.integrations.trialRunEmptyPrompt',
              '保存前可先调试，验证输出指标'
            )}
          >
            <Button
              type="primary"
              className="mt-3"
              icon={<PlayCircleOutlined />}
              loading={trialBusy}
              disabled={!nodeSelected || trialBusy}
              onClick={handleTrialClick}
            >
              {t('monitor.integrations.trialRun', '调试')}
            </Button>
          </CompactEmptyState>
        </div>
      </div>
    );
  }

  // 2. 运行中状态 (Spin)
  if (isSpinning) {
    return (
      <div className="mt-4 mb-4 rounded-lg border border-[var(--color-border-1)] bg-[var(--color-bg-1)] p-4">
        <div className="flex items-center justify-between mb-3 border-b border-[var(--color-border-1)] pb-2">
          <div className="flex items-center gap-2">
            <DashboardOutlined className="text-[var(--color-primary)] text-[15px]" />
            <b className="text-[14px] text-[var(--color-text-1)]">
              {t('monitor.integrations.trialRunAreaTitle', '调试结果')}
            </b>
            {instanceName && (
              <Tag className="ml-1 text-[12px]">{instanceName}</Tag>
            )}
          </div>
          <Button size="small" disabled loading icon={<ReloadOutlined />}>
            {t('monitor.integrations.reTrialRun', '重新调试')}
          </Button>
        </div>
        {catalogErrorAlert}
        <div className="flex flex-col items-center justify-center py-10 px-4 rounded-md border border-[var(--color-border-1)] bg-[var(--color-bg-2)]">
          <Spin
            tip={
              <span className="mt-2 text-[13px] text-[var(--color-text-2)] font-medium">
                {t(
                  'monitor.integrations.trialRunSpinning',
                  '调试中，不会写入时序库'
                )}
              </span>
            }
          >
            <div className="h-10 w-48" />
          </Spin>
        </div>
      </div>
    );
  }

  // 3. 告警警告状态 (Alert warning: no permission / rate limit)
  if (task.status === 'warning' || task.warning_type) {
    const isRateLimit = task.warning_type === 'rate_limit';
    const isNoPermission = task.warning_type === 'no_permission';
    const warningMsg = isRateLimit
      ? t('monitor.integrations.trialRunRateLimit', '调试过于频繁，请稍后重试')
      : isNoPermission
        ? t('monitor.integrations.trialRunNoPermission', '当前账号无权调试该对象/节点')
        : task.error_message || t('monitor.integrations.trialRunWarning', '调试提示');

    return (
      <div className="mt-4 mb-4 rounded-lg border border-[var(--color-border-1)] bg-[var(--color-bg-1)] p-4">
        <div className="flex items-center justify-between mb-3 border-b border-[var(--color-border-1)] pb-2">
          <div className="flex items-center gap-2">
            <DashboardOutlined className="text-[var(--color-primary)] text-[15px]" />
            <b className="text-[14px] text-[var(--color-text-1)]">
              {t('monitor.integrations.trialRunAreaTitle', '调试结果')}
            </b>
            {instanceName && (
              <Tag className="ml-1 text-[12px]">{instanceName}</Tag>
            )}
          </div>
          <Button
            size="small"
            icon={<ReloadOutlined />}
            loading={trialSubmitting}
            disabled={!nodeSelected || trialBusy}
            onClick={handleTrialClick}
          >
            {t('monitor.integrations.reTrialRun', '重新调试')}
          </Button>
        </div>
        {catalogErrorAlert}
        <Alert
          type="warning"
          showIcon
          icon={<ExclamationCircleFilled />}
          message={warningMsg}
          description={
            <div className="mt-1 space-y-2">
              {task.error_message && task.error_message !== warningMsg ? (
                <div className="text-xs text-[var(--color-text-2)]">
                  {task.error_message}
                </div>
              ) : null}
              <TrialActionsBlockedNote />
            </div>
          }
        />
      </div>
    );
  }

  // 4. 失败状态 (Alert error: non-zero exit / timeout / parse fail / truncated / node unavailable)
  if (
    task.status === 'failed' ||
    isNonZeroExit ||
    parsedOutput?.isTimeout ||
    parsedOutput?.isNodeUnavailable
  ) {
    let errorTitle = t('monitor.integrations.trialRunNonZeroExit', '脚本执行失败（退出码 {code}）', {
      code: task.result?.exit_code ?? 1
    });
    let errorDesc =
      task.result?.stderr ||
      task.result?.stdout ||
      task.error_message ||
      t('monitor.integrations.trialRunNonZeroExitDesc', '脚本非零退出，请检查脚本内容或参数');

    if (parsedOutput?.isTimeout) {
      errorTitle = t('monitor.integrations.trialRunTimeout', '调试超时');
      errorDesc = t(
        'monitor.integrations.trialRunTimeoutDesc',
        '脚本执行超过限制时间，请检查脚本中是否存在长时间阻塞操作'
      );
    } else if (parsedOutput?.isNodeUnavailable) {
      errorTitle = t('monitor.integrations.trialRunNodeUnavailable', '采集节点不可用');
      errorDesc =
        task.error_message ||
        t('monitor.integrations.trialRunNodeUnavailableDesc', '采集节点离线或 Telegraf 运行环境异常，请检查节点状态');
    } else if (task.status === 'failed' && !isNonZeroExit) {
      errorTitle = t('monitor.integrations.trialRunFailed', '调试未通过');
      errorDesc =
        task.error_message ||
        t(
          'monitor.integrations.trialRunParseFailDesc',
          '脚本输出格式不符合规范，无法解析为时序指标'
        );
    }

    const stderr = task.result?.stderr || task.error_message;
    const stdout = task.result?.stdout;

    return (
      <div className="mt-4 mb-4 rounded-lg border border-[var(--color-border-1)] bg-[var(--color-bg-1)] p-4">
        <div className="flex items-center justify-between mb-3 border-b border-[var(--color-border-1)] pb-2">
          <div className="flex items-center gap-2">
            <DashboardOutlined className="text-[var(--color-primary)] text-[15px]" />
            <b className="text-[14px] text-[var(--color-text-1)]">
              {t('monitor.integrations.trialRunAreaTitle', '调试结果')}
            </b>
            {instanceName && (
              <Tag className="ml-1 text-[12px]">{instanceName}</Tag>
            )}
          </div>
          <Button
            size="small"
            icon={<ReloadOutlined />}
            loading={trialSubmitting}
            disabled={!nodeSelected || trialBusy}
            onClick={handleTrialClick}
          >
            {t('monitor.integrations.reTrialRun', '重新调试')}
          </Button>
        </div>
        {catalogErrorAlert}
        <Alert
          type="error"
          showIcon
          icon={<CloseCircleFilled />}
          message={errorTitle}
          description={
            <div className="mt-2 space-y-2">
              <div className="text-xs text-[var(--color-text-2)]">{errorDesc}</div>
              <TrialActionsBlockedNote />
              {parsedOutput?.isTruncated && (
                <div className="text-xs text-[var(--color-warning)] font-medium">
                  {t('monitor.integrations.trialRunTruncated', '输出结果已被截断')}
                </div>
              )}
              {stderr && (
                <div className="mt-1">
                  <div className="text-[11px] font-mono text-[var(--color-text-3)] mb-1">stderr:</div>
                  <pre className="script-debug-terminal m-0 max-h-[200px] overflow-auto rounded p-3 font-mono text-xs leading-5 whitespace-pre-wrap">
                    {stderr}
                  </pre>
                </div>
              )}
              {stdout && (
                <div className="mt-1">
                  <div className="text-[11px] font-mono text-[var(--color-text-3)] mb-1">stdout:</div>
                  <pre className="script-debug-terminal m-0 max-h-[200px] overflow-auto rounded p-3 font-mono text-xs leading-5 whitespace-pre-wrap">
                    {stdout}
                  </pre>
                </div>
              )}
            </div>
          }
        />
      </div>
    );
  }

  // 5. 成功后无指标状态 (Empty after run with no metrics +「重新调试」)
  if (!parsedOutput?.hasMetrics) {
    return (
      <div className="mt-4 mb-4 rounded-lg border border-[var(--color-border-1)] bg-[var(--color-bg-1)] p-4">
        <div className="flex items-center justify-between mb-3 border-b border-[var(--color-border-1)] pb-2">
          <div className="flex items-center gap-2">
            <DashboardOutlined className="text-[var(--color-primary)] text-[15px]" />
            <b className="text-[14px] text-[var(--color-text-1)]">
              {t('monitor.integrations.trialRunAreaTitle', '调试结果')}
            </b>
            {instanceName && (
              <Tag className="ml-1 text-[12px]">{instanceName}</Tag>
            )}
          </div>
          <Button
            size="small"
            icon={<ReloadOutlined />}
            loading={trialSubmitting}
            disabled={!nodeSelected || trialBusy}
            onClick={handleTrialClick}
          >
            {t('monitor.integrations.reTrialRun', '重新调试')}
          </Button>
        </div>
        {catalogErrorAlert}
        {/* 仍展示自身指标概览 */}
        <div className="grid grid-cols-3 gap-3 mb-4">
          <div className="p-3 rounded-md border border-[var(--color-border-1)] bg-[var(--color-bg-2)]">
            <div className="text-[12px] text-[var(--color-text-3)] font-medium">up (运行状态)</div>
            <div className="mt-1 text-[16px] font-bold text-[var(--color-success)] flex items-center gap-1">
              <CheckCircleFilled className="text-[14px]" /> 1 (正常)
            </div>
          </div>
          <div className="p-3 rounded-md border border-[var(--color-border-1)] bg-[var(--color-bg-2)]">
            <div className="text-[12px] text-[var(--color-text-3)] font-medium">duration (执行耗时)</div>
            <div className="mt-1 text-[16px] font-bold text-[var(--color-text-1)] font-mono">
              {parsedOutput?.selfMetrics?.duration_ms !== undefined
                ? `${parsedOutput.selfMetrics.duration_ms} ms`
                : '--'}
            </div>
          </div>
          <div className="p-3 rounded-md border border-[var(--color-border-1)] bg-[var(--color-bg-2)]">
            <div className="text-[12px] text-[var(--color-text-3)] font-medium">exit_code (退出码)</div>
            <div className="mt-1 text-[16px] font-bold text-[var(--color-text-1)] font-mono">0</div>
          </div>
        </div>
        <div className="flex flex-col items-center justify-center py-6 px-4 rounded-md border border-dashed border-[var(--color-border-2)] bg-[var(--color-bg-2)]">
          <CompactEmptyState
            description={t(
              'monitor.integrations.trialRunEmptyMetrics',
              '调试完成，未检测到输出指标'
            )}
          />
        </div>
      </div>
    );
  }

  // 6. 成功且有指标状态 (Self-metrics vs Business metrics)
  const businessMetrics = parsedOutput.businessMetrics;
  const selectableMetrics = businessMetrics.filter(
    (m) => !isReservedScriptMetricId(m.name)
  );
  const allChecked =
    selectableMetrics.length > 0 &&
    selectableMetrics.every((m) => selectedMetrics[m.key] !== false);
  const indeterminate =
    selectableMetrics.some((m) => selectedMetrics[m.key] !== false) &&
    !allChecked;

  return (
    <div className="mt-4 mb-4 rounded-lg border border-[var(--color-border-1)] bg-[var(--color-bg-1)] p-4">
      <div className="flex items-center justify-between mb-3 border-b border-[var(--color-border-1)] pb-2">
        <div className="flex items-center gap-2">
          <DashboardOutlined className="text-[var(--color-primary)] text-[15px]" />
          <b className="text-[14px] text-[var(--color-text-1)]">
            {t('monitor.integrations.trialRunAreaTitle', '调试结果')}
          </b>
          {instanceName && (
            <Tag className="ml-1 text-[12px]">{instanceName}</Tag>
          )}
          {parsedOutput.isTruncated && (
            <Tooltip
              title={t(
                'monitor.integrations.trialRunTruncatedDesc',
                '脚本输出超过大小限制，仅保留部分输出'
              )}
            >
              <Tag color="warning" className="text-[12px]">
                {t('monitor.integrations.trialRunTruncated', '输出结果已被截断')}
              </Tag>
            </Tooltip>
          )}
        </div>
        <Button
          size="small"
          icon={<ReloadOutlined />}
          loading={trialSubmitting}
          disabled={!nodeSelected || trialBusy}
          onClick={handleTrialClick}
        >
          {t('monitor.integrations.reTrialRun', '重新调试')}
        </Button>
      </div>

      {/* 自监控指标仅展示，不可勾选落库 */}
      <div className="mb-4" aria-disabled="true">
        <div className="text-[12px] font-medium text-[var(--color-text-3)] mb-2">
          {t('monitor.integrations.trialRunSelfMetrics', '自监控指标')}
        </div>
        <div className="grid grid-cols-3 gap-3">
          <div className="p-3 rounded-md border border-[var(--color-border-1)] bg-[var(--color-bg-2)]">
            <div className="text-[12px] text-[var(--color-text-3)]">up (运行状态)</div>
            <div className="mt-1 text-[16px] font-bold text-[var(--color-success)] flex items-center gap-1">
              <CheckCircleFilled className="text-[14px]" /> 1 (正常)
            </div>
          </div>
          <div className="p-3 rounded-md border border-[var(--color-border-1)] bg-[var(--color-bg-2)]">
            <div className="text-[12px] text-[var(--color-text-3)]">duration (执行耗时)</div>
            <div className="mt-1 text-[16px] font-bold text-[var(--color-text-1)] font-mono">
              {parsedOutput.selfMetrics.duration_ms !== undefined
                ? `${parsedOutput.selfMetrics.duration_ms} ms`
                : '--'}
            </div>
          </div>
          <div className="p-3 rounded-md border border-[var(--color-border-1)] bg-[var(--color-bg-2)]">
            <div className="text-[12px] text-[var(--color-text-3)]">exit_code (退出码)</div>
            <div className="mt-1 text-[16px] font-bold text-[var(--color-text-1)] font-mono">0</div>
          </div>
        </div>
      </div>

      {/* Business metrics with trial-run checkboxes */}
      <div>
        {catalogErrorAlert}
        <div className="flex items-center justify-between mb-2">
          <div className="flex items-center gap-2">
            <Checkbox
              checked={allChecked}
              indeterminate={indeterminate}
              onChange={(e) => toggleAllMetrics(e.target.checked)}
            />
            <span className="text-[12px] font-medium text-[var(--color-text-2)]">
              {t('monitor.integrations.trialRunBusinessMetrics', '业务指标')} (
              {selectableMetrics.filter((m) => selectedMetrics[m.key] !== false).length}/
              {selectableMetrics.length})
            </span>
          </div>
        </div>
        <div className="rounded-md border border-[var(--color-border-1)] overflow-hidden bg-[var(--color-bg)]">
          <div className="overflow-x-auto">
            <div className={BUSINESS_METRIC_TABLE_MIN_WIDTH}>
              <div
                className={`${BUSINESS_METRIC_GRID} border-b border-[var(--color-border-1)] bg-[var(--color-fill-1)] py-2 text-[12px] font-medium text-[var(--color-text-2)]`}
              >
                <div />
                <div className="min-w-0">{t('monitor.integrations.trialRunMetricId', '指标 ID')}</div>
                <div className="min-w-0">{t('monitor.integrations.trialRunMetricDimensions', '维度')}</div>
                <div className="min-w-0">{t('monitor.integrations.metricGroup', '分组')}</div>
                <div className="min-w-0">{t('common.unit', '单位')}</div>
                <div className="min-w-0 text-right">
                  {t('monitor.integrations.trialRunMetricValue', '采样值')}
                </div>
              </div>
              <div className="max-h-[360px] overflow-y-auto overflow-x-hidden divide-y divide-[var(--color-border-1)]">
                {businessMetrics.map((item: BusinessMetricItem) => {
                  const reservedMetricId = isReservedScriptMetricId(item.name);
                  const isChecked =
                    !reservedMetricId && selectedMetrics[item.key] !== false;
                  const catalog = catalogByKey[item.key] || {};
                  const existingEnum =
                    String(
                      catalog.data_type ||
                        existingByName.get(cleanMeasurementName(item.name))
                          ?.data_type ||
                        ''
                    ).toLowerCase() === 'enum';
                  const visibleDimensionNames = unionVisibleDimensionNames(
                    item.tags,
                    item.samples
                  );
                  const sampleCount = item.samples?.length || 1;
                  const showSamplePreview = visibleDimensionNames.length > 0;
                  const previewSamples =
                    item.samples?.length
                      ? item.samples
                      : [{ value: item.value, tags: item.tags }];
                  const sampleStack = (
                    <div className={SAMPLE_VALUE_STACK_CLASS}>
                      <div className="h-4 min-w-0 truncate text-right font-mono text-xs leading-4 tabular-nums text-[var(--color-text-3)]">
                        {String(item.value)}
                      </div>
                      <div className="h-4 min-w-0 truncate text-right text-[11px] leading-4 text-[var(--color-text-3)]">
                        {showSamplePreview
                          ? t(
                            'monitor.integrations.trialRunSampleCount',
                            '共 {count} 条',
                            { count: sampleCount }
                          )
                          : '\u00a0'}
                      </div>
                    </div>
                  );
                  return (
                    <div
                      key={item.key}
                      className={`${BUSINESS_METRIC_GRID} py-2 text-[13px] hover:bg-[var(--color-fill-2)] transition-colors ${
                        isChecked ? '' : 'opacity-60 bg-[var(--color-bg-2)]'
                      }`}
                    >
                      <div className="flex items-center justify-center">
                        <Checkbox
                          checked={isChecked}
                          disabled={reservedMetricId}
                          onChange={() => toggleMetric(item.key, reservedMetricId)}
                        />
                      </div>
                      <div className="min-w-0">
                        <EllipsisWithTooltip
                          className="truncate font-mono text-xs font-medium text-[var(--color-text-1)]"
                          text={item.name}
                        />
                        {reservedMetricId ? (
                          <div
                            className="mt-0.5 text-[11px] text-[var(--color-fail)]"
                            role="alert"
                          >
                            {t(
                              'monitor.integrations.reservedMetricId',
                              '指标 ID 与保留字段冲突，请更换'
                            )}
                          </div>
                        ) : null}
                      </div>
                      <div className="min-w-0">
                        <DimensionTagLine names={visibleDimensionNames} />
                        {Boolean(item.reservedTagKeys?.length) && (
                          <div
                            className="mt-0.5 text-[11px] text-[var(--color-fail)]"
                            role="alert"
                          >
                            {t('monitor.integrations.reservedTagRename', '保留字段，请换名')}
                          </div>
                        )}
                      </div>
                      <div className="min-w-0">
                        <ScriptMetricGroupSelect
                          size="middle"
                          allowClear
                          disabled={!isChecked || catalogError}
                          className={INLINE_CONTROL_CLASS}
                          placeholder={t('monitor.integrations.metricGroup', '分组')}
                          value={
                            typeof catalog.metric_group === 'number'
                              ? catalog.metric_group
                              : undefined
                          }
                          groups={groupOptions}
                          onGroupsChange={setGroupOptions}
                          objectId={objectId}
                          pluginId={pluginId}
                          onChange={(next) =>
                            updateCatalog(item.key, {
                              metric_group: typeof next === 'number' ? next : null,
                              editedGroup: true
                            })
                          }
                        />
                      </div>
                      <div className="min-w-0">
                        <Cascader
                          size="middle"
                          allowClear
                          disabled={!isChecked || existingEnum || catalogError}
                          className={INLINE_CONTROL_CLASS}
                          placeholder={t('common.unit', '单位')}
                          options={unitOptions}
                          displayRender={(labels) => {
                            const leaf = labels[labels.length - 1];
                            return leaf == null ? '' : String(leaf);
                          }}
                          showSearch={{
                            filter: (inputValue, path) => {
                              const needle = inputValue.trim().toLowerCase();
                              if (!needle) return true;
                              return path.some((option) => {
                                const label = String(option.label ?? '').toLowerCase();
                                const extra = String(
                                  (option as { searchText?: string }).searchText ?? ''
                                ).toLowerCase();
                                return label.includes(needle) || extra.includes(needle);
                              });
                            }
                          }}
                          value={
                            Array.isArray(catalog.unit)
                              ? catalog.unit.map((unit) => String(unit))
                              : undefined
                          }
                          onChange={(value) =>
                            updateCatalog(item.key, {
                              unit: Array.isArray(value) ? value : undefined,
                              editedUnit: true
                            })
                          }
                        />
                      </div>
                      <div className="min-w-0">
                        {showSamplePreview ? (
                          <Tooltip
                            placement="leftTop"
                            autoAdjustOverflow={false}
                            styles={{ body: { padding: 8 } }}
                            title={(
                              <SamplePreviewTable samples={previewSamples} />
                            )}
                          >
                            {sampleStack}
                          </Tooltip>
                        ) : (
                          sampleStack
                        )}
                      </div>
                    </div>
                  );
                })}
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
};

export default ScriptTrialRunArea;
