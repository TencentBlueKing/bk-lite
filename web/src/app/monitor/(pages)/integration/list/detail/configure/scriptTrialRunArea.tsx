import React, { useMemo, useState, useEffect, useRef } from 'react';
import { Alert, Button, Cascader, Checkbox, Input, Select, Spin, Tag, Tooltip } from 'antd';
import {
  CheckCircleFilled,
  CloseCircleFilled,
  ExclamationCircleFilled,
  ReloadOutlined,
  PlayCircleOutlined,
  DashboardOutlined
} from '@ant-design/icons';
import CompactEmptyState from '@/components/compact-empty-state';
import { useTranslation } from '@/utils/i18n';
import useApiClient from '@/utils/request';
import { useCommon } from '@/app/monitor/context/common';
import { parseScriptMetrics, BusinessMetricItem, cleanDisplayTags } from './scriptMetricsParser';
import {
  applyDefaultCatalogDrafts,
  buildUnitCascaderOptions,
  extractCatalogItems,
  formatDimensionTagSummary,
  mergeRetainedTrialMetricState,
  pickSelectedBusinessMetrics,
  resolveDefaultCatalogGroupId,
  resolveDefaultCatalogUnitPath,
  CatalogMetricGroupOption,
  ScriptMetricCatalogDraft
} from './scriptMetricPersist';
import ScriptMetricGroupSelect from './scriptMetricGroupSelect';

const BUSINESS_METRIC_GRID =
  'grid-cols-[36px_minmax(148px,1.15fr)_minmax(148px,1.15fr)_minmax(108px,0.75fr)_minmax(72px,0.5fr)_minmax(120px,0.9fr)_minmax(128px,0.95fr)_minmax(140px,1.05fr)]';

const DimensionTagLine: React.FC<{ tags?: Record<string, string> }> = ({
  tags
}) => {
  const displayTags = cleanDisplayTags(tags);
  const entries = Object.entries(displayTags || {});
  if (!entries.length) {
    return null;
  }
  const summary = formatDimensionTagSummary(displayTags);
  return (
    <Tooltip title={summary}>
      <div className="mt-0.5 min-w-0 overflow-hidden text-ellipsis whitespace-nowrap">
        {entries.map(([key, value]) => (
          <Tag
            key={key}
            className="m-0 mr-1 inline-block text-[11px] font-mono leading-4 py-0 px-1"
          >
            {key}={value}
          </Tag>
        ))}
      </div>
    </Tooltip>
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
  onDebugBusinessMetricsChange?: (metrics: BusinessMetricItem[]) => void;
  onBusinessMetricsAvailableChange?: (available: boolean) => void;
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
  onDebugBusinessMetricsChange,
  onBusinessMetricsAvailableChange
}) => {
  const { t } = useTranslation();
  const { get } = useApiClient();
  const commonContext = useCommon();
  const [selectedMetrics, setSelectedMetrics] = useState<Record<string, boolean>>({});
  const [catalogByKey, setCatalogByKey] = useState<Record<string, ScriptMetricCatalogDraft>>({});
  const [groupOptions, setGroupOptions] = useState<CatalogMetricGroupOption[]>([]);
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
  const defaultUnitPath = useMemo(
    () => resolveDefaultCatalogUnitPath(unitOptions),
    [unitOptions]
  );

  useEffect(() => {
    retainedMetricStateRef.current.selected = selectedMetrics;
  }, [selectedMetrics]);

  useEffect(() => {
    retainedMetricStateRef.current.catalog = catalogByKey;
  }, [catalogByKey]);

  // 重新调试成功：刷新采样值；仍存在的指标保留勾选/分组/单位/描述；消失的视为未勾选。
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
    const merged = mergeRetainedTrialMetricState({
      nextMetrics: metrics,
      prevSelected: retainedMetricStateRef.current.selected,
      prevCatalog: retainedMetricStateRef.current.catalog
    });
    const withDefaults = applyDefaultCatalogDrafts(
      metrics,
      merged.catalog,
      defaultGroupId,
      defaultUnitPath
    );
    const next = { selected: merged.selected, catalog: withDefaults.catalog };
    retainedMetricStateRef.current = next;
    setSelectedMetrics(next.selected);
    setCatalogByKey(next.catalog);
  }, [parsedOutput, defaultGroupId, defaultUnitPath]);

  useEffect(() => {
    if (!pluginId || !objectId) {
      setGroupOptions([]);
      return;
    }
    let cancelled = false;
    const loadGroups = async () => {
      try {
        const groupRes = await get('/monitor/api/metrics_group/', {
          params: {
            monitor_object_id: objectId,
            monitor_plugin_id: pluginId,
            page: 1,
            page_size: 100
          },
          suppressErrorNotification: true
        });
        if (!cancelled) {
          setGroupOptions(extractCatalogItems<CatalogMetricGroupOption>(groupRes));
        }
      } catch {
        if (!cancelled) {
          setGroupOptions([]);
        }
      }
    };
    void loadGroups();
    return () => {
      cancelled = true;
    };
  }, [get, pluginId, objectId]);

  // 仅成功调试把勾选业务指标交给确认；失败即使解析到行也不喂。
  useEffect(() => {
    if (!onSelectedMetricsChange) return;
    if (!canFeedScriptMetricActions || !parsedOutput?.businessMetrics?.length) {
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
    canFeedScriptMetricActions,
    selectedMetrics,
    parsedOutput,
    catalogByKey,
    onSelectedMetricsChange
  ]);

  // 覆盖删除以「本次调试结果里出现过的业务指标」为保留集，含未勾选行。
  useEffect(() => {
    if (!onDebugBusinessMetricsChange) return;
    if (!canFeedScriptMetricActions || !parsedOutput?.businessMetrics?.length) {
      onDebugBusinessMetricsChange([]);
      return;
    }
    onDebugBusinessMetricsChange(parsedOutput.businessMetrics);
  }, [
    canFeedScriptMetricActions,
    parsedOutput,
    onDebugBusinessMetricsChange
  ]);

  useEffect(() => {
    onBusinessMetricsAvailableChange?.(
      canFeedScriptMetricActions &&
        (parsedOutput?.businessMetrics?.length || 0) > 0
    );
  }, [
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

  const toggleMetric = (key: string) => {
    if (isSpinning) return;
    setSelectedMetrics((prev) => ({
      ...prev,
      [key]: !prev[key]
    }));
  };

  const toggleAllMetrics = (checked: boolean) => {
    if (isSpinning || !parsedOutput?.businessMetrics) return;
    const nextMap: Record<string, boolean> = {};
    parsedOutput.businessMetrics.forEach((m) => {
      nextMap[m.key] = checked;
    });
    setSelectedMetrics(nextMap);
  };

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
  const allChecked =
    businessMetrics.length > 0 && businessMetrics.every((m) => selectedMetrics[m.key] !== false);
  const indeterminate =
    businessMetrics.some((m) => selectedMetrics[m.key] !== false) && !allChecked;

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
        <div className="flex items-center justify-between mb-2">
          <div className="flex items-center gap-2">
            <Checkbox
              checked={allChecked}
              indeterminate={indeterminate}
              onChange={(e) => toggleAllMetrics(e.target.checked)}
            />
            <span className="text-[12px] font-medium text-[var(--color-text-2)]">
              {t('monitor.integrations.trialRunBusinessMetrics', '业务指标')} (
              {businessMetrics.filter((m) => selectedMetrics[m.key] !== false).length}/
              {businessMetrics.length})
            </span>
          </div>
        </div>
        <div className="rounded-md border border-[var(--color-border-1)] overflow-hidden bg-[var(--color-bg)]">
          <div className="overflow-x-auto">
            <div
              className={`grid ${BUSINESS_METRIC_GRID} min-w-[1080px] border-b border-[var(--color-border-1)] bg-[var(--color-fill-1)] px-3 py-2 text-[12px] font-medium text-[var(--color-text-2)]`}
            >
              <div />
              <div>{t('monitor.integrations.trialRunMetricId', '指标 ID')}</div>
              <div>{t('monitor.integrations.trialRunMetricName', '指标名称')}</div>
              <div>{t('monitor.integrations.dataType', '数据类型')}</div>
              <div>{t('monitor.integrations.trialRunMetricValue', '采样值')}</div>
              <div>{t('monitor.integrations.metricGroup', '分组')}</div>
              <div>{t('common.unit', '单位')}</div>
              <div>{t('monitor.integrations.trialRunMetricDescription', '指标描述')}</div>
            </div>
            <div className="max-h-[360px] min-w-[1080px] overflow-auto divide-y divide-[var(--color-border-1)]">
              {businessMetrics.map((item: BusinessMetricItem) => {
                const isChecked = selectedMetrics[item.key] !== false;
                const catalog = catalogByKey[item.key] || {};
                return (
                  <div
                    key={item.key}
                    className={`grid ${BUSINESS_METRIC_GRID} items-center px-3 py-2 text-[13px] hover:bg-[var(--color-fill-2)] transition-colors ${
                      isChecked ? '' : 'opacity-60 bg-[var(--color-bg-2)]'
                    }`}
                  >
                    <div>
                      <Checkbox
                        checked={isChecked}
                        onChange={() => toggleMetric(item.key)}
                      />
                    </div>
                    <div className="min-w-0 pr-2">
                      <div
                        className="truncate font-mono text-xs font-medium text-[var(--color-text-1)]"
                        title={item.name}
                      >
                        {item.name}
                      </div>
                      <DimensionTagLine tags={item.tags} />
                      {Boolean(item.reservedTagKeys?.length) && (
                        <div
                          className="mt-0.5 text-[11px] text-[var(--color-fail)]"
                          role="alert"
                        >
                          {t('monitor.integrations.reservedTagRename', '保留字段，请换名')}
                        </div>
                      )}
                    </div>
                    <div className="min-w-0 pr-1">
                      <Input
                        size="small"
                        disabled={!isChecked}
                        className="w-full"
                        maxLength={100}
                        placeholder={item.name}
                        value={
                          catalog.display_name !== undefined
                            ? catalog.display_name
                            : item.name
                        }
                        onChange={(event) =>
                          updateCatalog(item.key, {
                            display_name: event.target.value
                          })
                        }
                      />
                    </div>
                    <div className="min-w-0 pr-1">
                      <Select
                        size="small"
                        disabled={!isChecked}
                        className="w-full"
                        value={catalog.data_type === 'Enum' ? 'Enum' : 'Number'}
                        options={[
                          {
                            value: 'Number',
                            label: t('monitor.integrations.number', '数字')
                          },
                          {
                            value: 'Enum',
                            label: t('monitor.integrations.enum', '枚举')
                          }
                        ]}
                        onChange={(value: 'Number' | 'Enum') =>
                          updateCatalog(item.key, { data_type: value })
                        }
                      />
                    </div>
                    <div
                      className="min-w-0 truncate font-mono text-xs text-[var(--color-text-2)]"
                      title={String(item.value)}
                    >
                      {String(item.value)}
                    </div>
                    <div className="min-w-0 pr-1">
                      <ScriptMetricGroupSelect
                        size="small"
                        allowClear
                        disabled={!isChecked}
                        className="w-full"
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
                            metric_group: typeof next === 'number' ? next : null
                          })
                        }
                      />
                    </div>
                    <div className="min-w-0 pr-1">
                      <Cascader
                        size="small"
                        allowClear
                        disabled={!isChecked}
                        className="w-full"
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
                            unit: Array.isArray(value) ? value : undefined
                          })
                        }
                      />
                    </div>
                    <div className="min-w-0">
                      <Input
                        size="small"
                        allowClear
                        disabled={!isChecked}
                        className="w-full"
                        placeholder={t(
                          'monitor.integrations.trialRunMetricDescription',
                          '指标描述'
                        )}
                        value={catalog.description || ''}
                        onChange={(event) =>
                          updateCatalog(item.key, {
                            description: event.target.value
                          })
                        }
                      />
                    </div>
                  </div>
                );
              })}
            </div>
          </div>
        </div>
      </div>
    </div>
  );
};

export default ScriptTrialRunArea;
