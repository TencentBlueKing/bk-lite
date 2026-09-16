import React, { useMemo } from 'react';
import { Form, Select, InputNumber, Input, Tooltip, Space, Tag } from 'antd';
import { QuestionCircleOutlined } from '@ant-design/icons';
import { useTranslation } from '@/utils/i18n';
import { ThresholdField } from '@/app/monitor/types';
import { StrategyFields } from '@/app/monitor/types/event';
import { useCommon } from '@/app/monitor/context/common';
import { SCHEDULE_UNIT_MAP, COMPARISON_METHOD } from '@/app/monitor/constants/event';
import { useMethodList } from '@/app/monitor/hooks/event';
import {
  COMPARE_MODE_ABSOLUTE,
  COMPARE_MODE_TIMELEFT,
  COUNT_IF_ALGORITHM,
  DEFAULT_FORECAST_LOOKBACK,
  FORECAST_LOOKBACK_OPTIONS,
  applySceneChip,
  buildPolicyRestatement,
  defaultCompareValueKind,
  formatUnitLabelWithRateSuffix,
  getAllowedRecoveryMethods,
  getAllowedThresholdMethods,
  getCompareModeSelectOptions,
  getCompareValueKinds,
  getMetricThresholdEnumState,
  getSceneChipStates,
  getThresholdUnitOptions,
  isVacantThresholdUnit,
  matchSceneChipId,
  resolveMetricDisplayUnit,
  shouldShowThresholdUnitSelector,
  timeleftRequiresLowSideThresholds,
  type SceneChipId
} from './strategyDetailUtils';
import ThresholdList from './thresholdList';

const { Option } = Select;
const COMPARE_KIND_SELECT_WIDTH = 108;

// 无数据告警级别选项
const NO_DATA_ALERT_OPTIONS = [
  { value: 'none', labelKey: 'noTriggerNoDataAlert' },
  { value: 'critical', labelKey: 'triggerCriticalAlert' },
  { value: 'error', labelKey: 'triggerErrorAlert' },
  { value: 'warning', labelKey: 'triggerWarningAlert' }
];

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
  onForecastLookbackChange?: (val: { type: string; value: number }) => void;
  recoveryThreshold?: { method?: string; value?: number | null };
  onRecoveryThresholdChange?: (val: {
    method?: string;
    value?: number | null;
  }) => void;
  metricLabel?: string | null;
  disableRateAlgorithm?: boolean;
  countPredicate?: { method?: string; value?: number | null } | null;
  onCountPredicateChange?: (val: { method: string; value: number | null }) => void;
  onSceneChipApply?: (payload: NonNullable<ReturnType<typeof applySceneChip>>) => void;
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
  forecastLookback,
  recoveryThreshold,
  metricLabel,
  disableRateAlgorithm,
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
  onForecastLookbackChange,
  onRecoveryThresholdChange,
  onCountPredicateChange,
  onSceneChipApply,
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

  // 验证阈值：仅在展示单位选择器时要求 thresholdUnit
  const validateThreshold = async () => {
    if (
      threshold.length &&
      (threshold.some((item) => {
        return !item.method;
      }) ||
        (showUnitSelector && !thresholdUnit))
    ) {
      return Promise.reject(new Error(t('monitor.events.thresholdValidate')));
    }
    if (
      compareMode === COMPARE_MODE_TIMELEFT &&
      !timeleftRequiresLowSideThresholds(compareMode, threshold)
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
  const flatCompareModes = useMemo(
    () => compareModeOptions.filter((item) => item.group === 'flat'),
    [compareModeOptions]
  );
  const offsetCompareModes = useMemo(
    () => compareModeOptions.filter((item) => item.group === 'offset'),
    [compareModeOptions]
  );
  const sceneChips = useMemo(
    () =>
      getSceneChipStates({
        isEnumMetric,
        isFormulaMode,
        disableRateAlgorithm,
        periodType: periodUnit,
        periodValue: period
      }),
    [isEnumMetric, isFormulaMode, disableRateAlgorithm, periodUnit, period]
  );
  const activeSceneChipId = matchSceneChipId({
    algorithm,
    compareMode,
    compareValueKind
  });
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
  const compareKindLabels: Record<string, string> = {
    delta: t('monitor.events.compareValueKindDelta'),
    percent: t('monitor.events.compareValueKindPercent'),
    ratio: t('monitor.events.compareValueKindRatio'),
    hours: t('monitor.events.compareValueKindHours')
  };
  const forecastTargetUnitLabel = useMemo(() => {
    // 容量线是源指标量纲（例如磁盘 B），不是剩余时间 hours。
    if (!metricUnit || isVacantThresholdUnit(metricUnit)) {
      return '';
    }
    const matched = unitList.find((item) => item.unit_id === metricUnit);
    return (
      resolveMetricDisplayUnit(metricUnit, unitList) ||
      matched?.unit_name ||
      ''
    );
  }, [metricUnit, unitList]);
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

  const handleSceneChipClick = (chipId: SceneChipId, disabled: boolean) => {
    if (disabled || !onSceneChipApply) {
      return;
    }
    const next = applySceneChip({
      chipId,
      algorithm,
      compareMode,
      compareValueKind,
      thresholds: threshold,
      recoveryThreshold,
      countPredicate
    });
    if (next) {
      onSceneChipApply(next);
    }
  };

  const renderCompareOption = (item: {
    value: string;
    disabled: boolean;
    reasonKey?: string;
  }) => (
    <Option key={item.value} value={item.value} disabled={item.disabled}>
      <Tooltip
        title={
          item.disabled && item.reasonKey ? t(item.reasonKey) : undefined
        }
      >
        <span className="flex w-full">
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
              <div className="mb-4 ml-[100px] flex flex-wrap items-center gap-2">
                <span className="text-[13px] leading-[22px] text-[var(--color-text-3)]">
                  {t('monitor.events.sceneChipCommon')}
                </span>
                {sceneChips.map((chip) => (
                  <Tooltip
                    key={chip.id}
                    title={
                      chip.disabled && chip.reasonKey
                        ? t(chip.reasonKey)
                        : undefined
                    }
                  >
                    <Tag.CheckableTag
                      checked={activeSceneChipId === chip.id}
                      className={`rounded-[6px]${chip.disabled ? ' cursor-not-allowed opacity-50' : ''}`}
                      onChange={() =>
                        handleSceneChipClick(chip.id, chip.disabled)
                      }
                    >
                      {t(chip.labelKey)}
                    </Tag.CheckableTag>
                  </Tooltip>
                ))}
              </div>
              {!isEnumMetric && (
                <Form.Item
                  label={
                    <span className="w-[100px]">
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
                      {flatCompareModes
                        .filter((item) => item.value !== COMPARE_MODE_TIMELEFT)
                        .map(renderCompareOption)}
                      {offsetCompareModes.length > 0 ? (
                        <Select.OptGroup
                          label={t('monitor.events.compareGroupOffset')}
                        >
                          {offsetCompareModes.map(renderCompareOption)}
                        </Select.OptGroup>
                      ) : null}
                      {flatCompareModes
                        .filter((item) => item.value === COMPARE_MODE_TIMELEFT)
                        .map(renderCompareOption)}
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
                          <Option key={kind} value={kind}>
                            {compareKindLabels[kind] || kind}
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
                      <span className="w-[100px]">
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
                          {forecastTargetUnitLabel ? (
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
                    label={
                      <span className="w-[100px]">
                        {t('monitor.events.forecastLookback')}
                      </span>
                    }
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
                name="threshold"
                label={
                  <span className="w-[100px]">
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
              <p className="mb-4 ml-[100px] text-[13px] leading-[22px] text-[var(--color-text-3)]">
                {restatement}
              </p>

              {/* 触发条件 */}
              <Form.Item<StrategyFields>
                label={
                  <span className="w-[100px]">
                    {t('monitor.events.triggerCondition')}
                  </span>
                }
              >
                {t('monitor.events.triggerConditionPrefix')}
                <Form.Item
                  name="trigger_count"
                  noStyle
                  rules={[
                    {
                      required: true,
                      message: t('common.required')
                    }
                  ]}
                >
                  <InputNumber
                    className="mx-[10px] w-[100px]"
                    min={1}
                    precision={0}
                  />
                </Form.Item>
                {t('monitor.events.triggerConditionSuffix')}
              </Form.Item>

              {/* 自动恢复 */}
              <Form.Item<StrategyFields>
                label={
                  <span className="w-[100px]">
                    {t('monitor.events.recovery')}
                  </span>
                }
              >
                {t('monitor.events.recoveryCondition')}
                <Form.Item name="recovery_condition" noStyle>
                  <InputNumber
                    className="mx-[10px] w-[100px]"
                    min={1}
                    precision={0}
                  />
                </Form.Item>
                {t('monitor.events.consecutivePeriods')}
              </Form.Item>
              <Form.Item
                label={
                  <span className="w-[100px]">
                    {t('monitor.events.recoveryThreshold')}
                  </span>
                }
              >
                <InputNumber
                  className="w-full"
                  style={{ width: '100%' }}
                  addonBefore={
                    <Select
                      allowClear
                      value={recoveryThreshold?.method || undefined}
                      popupMatchSelectWidth={false}
                      style={{ width: 80 }}
                      aria-label={t('monitor.events.method')}
                      onChange={(method) =>
                        onRecoveryThresholdChange?.({
                          method: method || '',
                          value: recoveryThreshold?.value ?? null
                        })
                      }
                    >
                      {allowedRecoveryMethods.map((item) => (
                        <Option key={item.value} value={item.value}>
                          {item.label}
                        </Option>
                      ))}
                    </Select>
                  }
                  addonAfter={recoveryThresholdUnitLabel || undefined}
                  placeholder={t(
                    'monitor.events.recoveryThresholdPlaceholder'
                  )}
                  value={recoveryThreshold?.value ?? null}
                  onChange={(value) =>
                    onRecoveryThresholdChange?.({
                      method: recoveryThreshold?.method || '',
                      value: typeof value === 'number' ? value : null
                    })
                  }
                />
              </Form.Item>

              {/* 无数据告警 */}
              <Form.Item
                label={
                  <span className="w-[100px]">
                    {t('monitor.events.noDataAlertLevel')}
                  </span>
                }
                extra={
                  functionDelayTip ? (
                    <span className="text-[12px] text-[var(--color-text-3)]">
                      {functionDelayTip}
                    </span>
                  ) : undefined
                }
              >
                {t('monitor.events.noDataAlertCondition')}
                <InputNumber
                  className="mx-[10px] w-[100px]"
                  min={SCHEDULE_UNIT_MAP[`${nodataUnit}Min`]}
                  max={SCHEDULE_UNIT_MAP[`${nodataUnit}Max`]}
                  value={noDataAlert}
                  precision={0}
                  onChange={onNoDataAlertChange}
                />
                {t('monitor.events.noDataAlertSuffix')}
                <Select
                  value={noDataAlertLevel}
                  popupMatchSelectWidth={false}
                  style={{ width: 200 }}
                  onChange={onNoDataAlertLevelChange}
                >
                  {NO_DATA_ALERT_OPTIONS.map((item) => (
                    <Option key={item.value} value={item.value}>
                      {t(`monitor.events.${item.labelKey}`)}
                    </Option>
                  ))}
                </Select>
              </Form.Item>
              <Form.Item
                label={
                  <span className="w-[100px]">
                    {t('monitor.events.noDataRecoveryWindow')}
                  </span>
                }
              >
                <InputNumber
                  className="mr-[10px] w-[100px]"
                  min={SCHEDULE_UNIT_MAP[`${noDataRecoveryUnit}Min`]}
                  max={SCHEDULE_UNIT_MAP[`${noDataRecoveryUnit}Max`]}
                  value={noDataRecovery}
                  precision={0}
                  onChange={onNoDataRecoveryChange}
                />
                {t('monitor.events.nodataRecover')}
              </Form.Item>

              {/* 无数据告警名称 - 条件显示 */}
              {showNoDataAlertName && (
                <Form.Item<StrategyFields>
                  name="no_data_alert_name"
                  label={
                    <span className="w-[100px]">
                      {t('monitor.events.noDataAlertName')}
                    </span>
                  }
                  rules={[
                    {
                      required: true,
                      message: t('common.required')
                    }
                  ]}
                >
                  <Input
                    style={{ width: '100%' }}
                    value={noDataAlertName}
                    placeholder={t('monitor.events.noDataAlertName')}
                    onChange={(e) => onNoDataAlertNameChange(e.target.value)}
                  />
                </Form.Item>
              )}
            </>
          )
        }
      </Form.Item>
    </>
  );
};

export default AlertConditionsForm;
