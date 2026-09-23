import React, { useEffect, useMemo } from 'react';
import { Form, Select, InputNumber, Tooltip, Space } from 'antd';
import { QuestionCircleOutlined } from '@ant-design/icons';
import { useTranslation } from '@/utils/i18n';
import { ThresholdField } from '@/app/monitor/types';
import { StrategyFields } from '@/app/monitor/types/event';
import { useCommon } from '@/app/monitor/context/common';
import { getMonitorUnitSelectLabel } from '@/app/monitor/components/monitor-shared/unit-label';
import { COMPARISON_METHOD } from '@/app/monitor/constants/event';
import { useMethodList } from '@/app/monitor/hooks/event';
import {
  COMPARE_MODE_ABSOLUTE,
  COMPARE_MODE_TIMELEFT,
  COUNT_IF_ALGORITHM,
  DEFAULT_FORECAST_LOOKBACK,
  FORECAST_LOOKBACK_OPTIONS,
  buildPolicyRestatement,
  defaultCompareValueKind,
  formatUnitLabelWithRateSuffix,
  getAllowedRecoveryMethods,
  completedThresholds,
  getAllowedThresholdMethods,
  getCompareModeSelectOptions,
  getCompareValueKinds,
  getMetricThresholdEnumState,
  getThresholdUnitOptions,
  isVacantThresholdUnit,
  resolveForecastTargetUnit,
  resolveMetricDisplayUnit,
  shouldShowThresholdUnitSelector,
  timeleftRequiresLowSideThresholds
} from './strategyDetailUtils';
import ThresholdList from './thresholdList';
import AlertDurationFields, {
  STRATEGY_CONDITION_LABEL_CLASS,
  STRATEGY_CONDITION_LABEL_WIDTH,
  strategyConditionLabelWithTip
} from './alertDurationFields';

const { Option } = Select;
const COMPARE_KIND_SELECT_WIDTH = 108;

interface AlertConditionsFormProps {
  enableAlerts: string[];
  threshold: ThresholdField[];
  calculationUnit: string | null;
  thresholdUnit: string | null;
  noDataAlert: number | null;
  nodataUnit: string;
  noDataRecovery: number | null;
  noDataRecoveryUnit: string;
  noDataAlertLevel: string;
  noDataAlertName: string;
  functionDelayMinutes: number | null;
  metricUnit: string | null;
  isFormulaMode: boolean;
  period: number | null;
  periodUnit: string;
  compareMode: string;
  compareValueKind: string;
  algorithm?: string | null;
  forecastTarget?: number | null;
  forecastTargetUnit?: string | null;
  forecastLookback?: { type: string; value: number };
  onEnableAlertsChange: (val: string[]) => void;
  onThresholdChange: (value: ThresholdField[]) => void;
  onThresholdUnitChange: (val: string) => void;
  onNodataUnitChange: (val: string) => void;
  onNoDataAlertChange: (e: number | null) => void;
  onNodataRecoveryUnitChange: (val: string) => void;
  onNoDataRecoveryChange: (e: number | null) => void;
  onNoDataAlertLevelChange: (val: string) => void;
  onNoDataAlertNameChange: (val: string) => void;
  onCompareModeChange: (val: string) => void;
  onCompareValueKindChange: (val: string) => void;
  onForecastTargetChange?: (val: number | null) => void;
  onForecastTargetUnitChange?: (val: string) => void;
  onForecastLookbackChange?: (val: { type: string; value: number }) => void;
  recoveryThreshold?: { method?: string; value?: number | null };
  onRecoveryThresholdChange?: (val: {
    method?: string;
    value?: number | null;
  }) => void;
  metricLabel?: string | null;
  monitorName?: string;
  countPredicate?: { method?: string; value?: number | null } | null;
  onCountPredicateChange?: (val: { method: string; value: number | null }) => void;
  isTrap: (getFieldValue: any) => boolean;
}

const AlertConditionsForm: React.FC<AlertConditionsFormProps> = ({
  threshold,
  calculationUnit,
  thresholdUnit,
  noDataAlert,
  nodataUnit,
  noDataRecovery,
  noDataRecoveryUnit,
  noDataAlertLevel,
  noDataAlertName,
  functionDelayMinutes,
  metricUnit,
  isFormulaMode,
  period,
  periodUnit,
  compareMode,
  compareValueKind,
  algorithm,
  forecastTarget,
  forecastTargetUnit,
  forecastLookback,
  recoveryThreshold,
  metricLabel,
  monitorName,
  countPredicate,
  onThresholdChange,
  onThresholdUnitChange,
  onNoDataAlertChange,
  onNoDataRecoveryChange,
  onNoDataAlertLevelChange,
  onNoDataAlertNameChange,
  onCompareModeChange,
  onCompareValueKindChange,
  onForecastTargetChange,
  onForecastTargetUnitChange,
  onForecastLookbackChange,
  onRecoveryThresholdChange,
  onCountPredicateChange,
  isTrap
}) => {
  const { t } = useTranslation();
  const commonContext = useCommon();
  const unitList = commonContext?.unitList || [];
  const METHOD_LIST = useMethodList();

  const { isEnumMetric, enumOptions } = useMemo(
    () => getMetricThresholdEnumState({ isFormulaMode, metricUnit }),
    [isFormulaMode, metricUnit]
  );

  // 阈值单位只由计算结果量纲约束，与当前选择的阈值展示单位解耦。
  const thresholdFilterBase = calculationUnit;

  const filteredUnitOptions = useMemo(
    () =>
      getThresholdUnitOptions({
        unitList,
        metricUnit: thresholdFilterBase,
        isEnumMetric,
        lockToExactUnit:
          compareValueKind === 'percent' ||
          compareValueKind === 'hours' ||
          algorithm === 'changes' ||
          algorithm === COUNT_IF_ALGORITHM ||
          algorithm === 'rate' ||
          algorithm === 'deriv'
      }),
    [unitList, thresholdFilterBase, isEnumMetric, compareValueKind, algorithm]
  );

  const showUnitSelector = shouldShowThresholdUnitSelector({
    isFormulaMode,
    isEnumMetric,
    calculationUnit: thresholdFilterBase,
    unitList
  });

  // 三个级别都展示，但只校验填了数值的行。空行忽略，至少一行即可提交。
  const validateThreshold = async () => {
    const filled = completedThresholds(threshold);
    if (!filled.length) {
      return Promise.reject(new Error(t('monitor.events.thresholdRequired')));
    }
    if (
      filled.some((item) => !item.method) ||
      (showUnitSelector && !thresholdUnit)
    ) {
      return Promise.reject(new Error(t('monitor.events.thresholdValidate')));
    }
    if (
      compareMode === COMPARE_MODE_TIMELEFT &&
      !timeleftRequiresLowSideThresholds(compareMode, filled)
    ) {
      return Promise.reject(
        new Error(t('monitor.events.timeleftThresholdValidate'))
      );
    }
    return Promise.resolve();
  };

  const compareModeOptions = useMemo(
    () =>
      getCompareModeSelectOptions({
        periodType: periodUnit,
        periodValue: period,
        algorithm
      }),
    [period, periodUnit, algorithm]
  );
  const compareKindOptions = useMemo(
    () => getCompareValueKinds(compareMode),
    [compareMode]
  );
  const allowedThresholdMethods = useMemo(
    () => getAllowedThresholdMethods(compareMode, COMPARISON_METHOD),
    [compareMode]
  );
  const allowedRecoveryMethods = useMemo(
    () => getAllowedRecoveryMethods(threshold, COMPARISON_METHOD),
    [threshold]
  );
  const algorithmLabel = useMemo(
    () =>
      METHOD_LIST.find((item) => String(item.value) === String(algorithm))
        ?.label || '',
    [METHOD_LIST, algorithm]
  );
  const compareModeLabels: Record<string, string> = {
    absolute: t('monitor.events.compareModeAbsolute'),
    previous_window: t('monitor.events.compareModePreviousWindow'),
    offset_1h: t('monitor.events.compareModeOffset1h'),
    offset_24h: t('monitor.events.compareModeOffset24h'),
    offset_7d: t('monitor.events.compareModeOffset7d'),
    offset_30d: t('monitor.events.compareModeOffset30d'),
    baseline_4w: t('monitor.events.compareModeBaseline4w'),
    timeleft: t('monitor.events.compareModeTimeleft')
  };
  const compareModeTips: Record<string, string> = {
    absolute: t('monitor.events.compareModeAbsoluteTip'),
    previous_window: t('monitor.events.compareModePreviousWindowTip'),
    offset_1h: t('monitor.events.compareModeOffset1hTip'),
    offset_24h: t('monitor.events.compareModeOffset24hTip'),
    offset_7d: t('monitor.events.compareModeOffset7dTip'),
    offset_30d: t('monitor.events.compareModeOffset30dTip'),
    baseline_4w: t('monitor.events.compareModeBaseline4wTip'),
    timeleft: t('monitor.events.compareModeTimeleftTip')
  };
  const compareKindLabels: Record<string, string> = {
    delta: t('monitor.events.compareValueKindDelta'),
    percent: t('monitor.events.compareValueKindPercent'),
    ratio: t('monitor.events.compareValueKindRatio'),
    hours: t('monitor.events.compareValueKindHours')
  };
  const compareKindTips: Record<string, string> = {
    delta: t('monitor.events.compareValueKindDeltaTip'),
    percent: t('monitor.events.compareValueKindPercentTip'),
    ratio: t('monitor.events.compareValueKindRatioTip'),
    hours: t('monitor.events.compareValueKindHoursTip')
  };
  const forecastUnitOptions = useMemo(() => {
    if (isFormulaMode || isEnumMetric) return [];
    return getThresholdUnitOptions({
      unitList,
      metricUnit,
      isEnumMetric: false
    });
  }, [isFormulaMode, isEnumMetric, unitList, metricUnit]);
  const resolvedForecastTargetUnit = useMemo(
    () =>
      resolveForecastTargetUnit({
        isFormulaMode,
        metricUnit,
        forecastTargetUnit,
        unitOptions: forecastUnitOptions
      }),
    [isFormulaMode, metricUnit, forecastTargetUnit, forecastUnitOptions]
  );
  const forecastTargetUnitLabel = useMemo(() => {
    // 容量线是源指标量纲（例如磁盘 B），不是剩余时间 hours。
    const unitId = resolvedForecastTargetUnit || metricUnit;
    if (!unitId || isVacantThresholdUnit(unitId)) {
      return '';
    }
    const matched = unitList.find((item) => item.unit_id === unitId);
    if (matched && (unitId === 'percent' || unitId === 'percentunit')) {
      return getMonitorUnitSelectLabel(matched);
    }
    return (
      resolveMetricDisplayUnit(unitId, unitList) ||
      matched?.unit_name ||
      ''
    );
  }, [resolvedForecastTargetUnit, metricUnit, unitList]);

  useEffect(() => {
    if (!forecastTargetUnit || !onForecastTargetUnitChange) return;
    if (forecastTargetUnit === resolvedForecastTargetUnit) return;
    onForecastTargetUnitChange(resolvedForecastTargetUnit);
  }, [
    forecastTargetUnit,
    resolvedForecastTargetUnit,
    onForecastTargetUnitChange
  ]);
  const recoveryThresholdUnitLabel = useMemo(() => {
    if (!thresholdUnit || isVacantThresholdUnit(thresholdUnit)) {
      return formatUnitLabelWithRateSuffix('', thresholdUnit, algorithm);
    }
    const matched = unitList.find((item) => item.unit_id === thresholdUnit);
    return formatUnitLabelWithRateSuffix(
      resolveMetricDisplayUnit(thresholdUnit, unitList) ||
        matched?.unit_name ||
        '',
      thresholdUnit,
      algorithm
    );
  }, [thresholdUnit, unitList, algorithm]);
  const restatement = useMemo(() => {
    const primary = threshold.find((item) => item.method && item.value != null) ||
      threshold[0];
    return buildPolicyRestatement({
      t,
      metricLabel,
      algorithmLabel,
      algorithm,
      compareMode,
      compareValueKind,
      compareModeLabel: compareModeLabels[compareMode] || '',
      thresholdMethod: primary?.method,
      thresholdValue:
        typeof primary?.value === 'number' ? primary.value : null,
      thresholdUnitLabel: recoveryThresholdUnitLabel,
      countPredicateMethod: countPredicate?.method,
      countPredicateValue:
        typeof countPredicate?.value === 'number' ? countPredicate.value : null,
      forecastTarget
    });
  }, [
    t,
    metricLabel,
    algorithmLabel,
    algorithm,
    compareMode,
    compareValueKind,
    compareModeLabels,
    threshold,
    recoveryThresholdUnitLabel,
    countPredicate,
    forecastTarget
  ]);

  const handleCompareModeChange = (val: string) => {
    onCompareModeChange(val);
    if (val === COMPARE_MODE_ABSOLUTE) {
      onCompareValueKindChange('');
      return;
    }
    const kinds = getCompareValueKinds(val);
    if (!kinds.includes(compareValueKind)) {
      onCompareValueKindChange(defaultCompareValueKind(val));
    }
  };

  const renderCompareOption = (item: {
    value: string;
    disabled: boolean;
    reasonKey?: string;
  }) => (
    <Option
      key={item.value}
      value={item.value}
      disabled={item.disabled}
      label={compareModeLabels[item.value] || item.value}
    >
      <Tooltip
        overlayInnerStyle={{ whiteSpace: 'pre-line' }}
        placement="right"
        title={
          item.disabled && item.reasonKey
            ? t(item.reasonKey)
            : compareModeTips[item.value]
        }
      >
        <span className="flex w-full min-w-0 items-center">
          {compareModeLabels[item.value] || item.value}
        </span>
      </Tooltip>
    </Option>
  );

  // 是否显示无数据告警名称（选择了非"不触发"的选项时显示）
  const showNoDataAlertName = noDataAlertLevel && noDataAlertLevel !== 'none';
  const functionDelayTip =
    showNoDataAlertName && functionDelayMinutes != null
      ? t(
        'monitor.events.noDataFunctionDelayTip',
        '当前指标使用了函数计算，预计存在约 {x} 分钟的数据延迟，请注意无数据告警的触发时间可能相应延后。',
        { x: functionDelayMinutes }
      )
      : undefined;

  return (
    <>
      <Form.Item
        noStyle
        shouldUpdate={(prevValues, currentValues) =>
          prevValues.collect_type !== currentValues.collect_type
        }
      >
        {({ getFieldValue }) =>
          isTrap(getFieldValue) ? null : (
            <>
              {!isEnumMetric && (
                <Form.Item
                  required
                  label={
                    <span className={STRATEGY_CONDITION_LABEL_CLASS}>
                      {t('monitor.events.compareBaseline')}
                    </span>
                  }
                >
                  <Space.Compact block>
                    <Select
                      value={compareMode}
                      onChange={handleCompareModeChange}
                      style={{
                        width:
                          compareKindOptions.length > 0
                            ? `calc(100% - ${COMPARE_KIND_SELECT_WIDTH}px)`
                            : '100%'
                      }}
                    >
                      {compareModeOptions.map(renderCompareOption)}
                    </Select>
                    {compareKindOptions.length > 0 ? (
                      <Select
                        value={
                          compareKindOptions.includes(compareValueKind)
                            ? compareValueKind
                            : defaultCompareValueKind(compareMode)
                        }
                        onChange={onCompareValueKindChange}
                        aria-label={t('monitor.events.compareValueKind')}
                        popupMatchSelectWidth={false}
                        style={{ width: COMPARE_KIND_SELECT_WIDTH }}
                      >
                        {compareKindOptions.map((kind) => (
                          <Option
                            key={kind}
                            value={kind}
                            label={compareKindLabels[kind] || kind}
                          >
                            <Tooltip
                              overlayInnerStyle={{ whiteSpace: 'pre-line' }}
                              placement="right"
                              title={compareKindTips[kind]}
                            >
                              <span className="flex w-full min-w-0 items-center">
                                {compareKindLabels[kind] || kind}
                              </span>
                            </Tooltip>
                          </Option>
                        ))}
                      </Select>
                    ) : null}
                  </Space.Compact>
                </Form.Item>
              )}
              {compareMode === COMPARE_MODE_TIMELEFT && !isEnumMetric && (
                <>
                  <Form.Item
                    required
                    label={
                      <span className={STRATEGY_CONDITION_LABEL_CLASS}>
                        {t('monitor.events.forecastTarget')}
                      </span>
                    }
                  >
                    <InputNumber
                      className="w-full"
                      style={{ width: '100%' }}
                      min={0}
                      value={forecastTarget}
                      placeholder={t('common.inputTip')}
                      addonAfter={
                        <span className="inline-flex items-center gap-1">
                          {forecastUnitOptions.length > 1 ? (
                            <Select
                              size="small"
                              popupMatchSelectWidth={false}
                              className="min-w-[5.5rem]"
                              aria-label={t('common.unit')}
                              value={resolvedForecastTargetUnit || undefined}
                              options={forecastUnitOptions.map((option) => ({
                                value: option.unit_id,
                                label:
                                  option.unit_id === 'percent' ||
                                  option.unit_id === 'percentunit'
                                    ? getMonitorUnitSelectLabel(option)
                                    : option.display_unit ||
                                      getMonitorUnitSelectLabel(option)
                              }))}
                              onChange={(value) =>
                                onForecastTargetUnitChange?.(value)
                              }
                            />
                          ) : forecastTargetUnitLabel ? (
                            <span>{forecastTargetUnitLabel}</span>
                          ) : null}
                          <Tooltip
                            title={t('monitor.events.forecastTargetTitle')}
                          >
                            <QuestionCircleOutlined className="text-[var(--color-text-3)]" />
                          </Tooltip>
                        </span>
                      }
                      onChange={(value) =>
                        onForecastTargetChange?.(
                          typeof value === 'number' ? value : null
                        )
                      }
                    />
                  </Form.Item>
                  <Form.Item
                    label={strategyConditionLabelWithTip(
                      t('monitor.events.forecastLookback'),
                      t('monitor.events.forecastLookbackTitle')
                    )}
                  >
                    <Select
                      className="w-full"
                      value={`${forecastLookback?.type || DEFAULT_FORECAST_LOOKBACK.type}:${forecastLookback?.value || DEFAULT_FORECAST_LOOKBACK.value}`}
                      onChange={(val) => {
                        const [type, rawValue] = val.split(':');
                        onForecastLookbackChange?.({
                          type,
                          value: Number(rawValue)
                        });
                      }}
                    >
                      {FORECAST_LOOKBACK_OPTIONS.map((item) => (
                        <Option
                          key={`${item.type}:${item.value}`}
                          value={`${item.type}:${item.value}`}
                        >
                          {t(`monitor.events.forecastLookback${item.value === 1 ? '1h' : item.value === 4 ? '4h' : '24h'}`)}
                        </Option>
                      ))}
                    </Select>
                  </Form.Item>
                </>
              )}

              {/* 告警阈值 */}
              <Form.Item<StrategyFields>
                required
                name="threshold"
                label={
                  <span className={STRATEGY_CONDITION_LABEL_CLASS}>
                    {t('monitor.events.alertThreshold')}
                  </span>
                }
                rules={[{ validator: validateThreshold }]}
              >
                <ThresholdList
                  data={threshold}
                  onChange={onThresholdChange}
                  thresholdUnit={thresholdUnit}
                  onThresholdUnitChange={onThresholdUnitChange}
                  unitOptions={filteredUnitOptions}
                  isEnumMetric={isEnumMetric}
                  enumOptions={enumOptions}
                  showUnitSelector={showUnitSelector}
                  allowedMethods={
                    isEnumMetric ? undefined : allowedThresholdMethods
                  }
                  unitAddonLabel={recoveryThresholdUnitLabel}
                />
              </Form.Item>
              <p
                className="mb-4 text-[13px] leading-[22px] text-[var(--color-text-3)]"
                style={{ marginLeft: STRATEGY_CONDITION_LABEL_WIDTH }}
              >
                {restatement}
              </p>
              <AlertDurationFields
                recoveryThreshold={recoveryThreshold}
                onRecoveryThresholdChange={onRecoveryThresholdChange}
                allowedRecoveryMethods={allowedRecoveryMethods}
                recoveryThresholdUnitLabel={recoveryThresholdUnitLabel}
                noDataAlert={noDataAlert}
                nodataUnit={nodataUnit}
                noDataRecovery={noDataRecovery}
                noDataRecoveryUnit={noDataRecoveryUnit}
                noDataAlertLevel={noDataAlertLevel}
                noDataAlertName={noDataAlertName}
                functionDelayTip={functionDelayTip}
                monitorName={monitorName}
                onNoDataAlertChange={onNoDataAlertChange}
                onNoDataRecoveryChange={onNoDataRecoveryChange}
                onNoDataAlertLevelChange={onNoDataAlertLevelChange}
                onNoDataAlertNameChange={onNoDataAlertNameChange}
              />
            </>
          )
        }
      </Form.Item>
    </>
  );
};

export default AlertConditionsForm;
