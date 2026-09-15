import React, { useMemo } from 'react';
import { Form, Select, InputNumber, Input } from 'antd';
import { useTranslation } from '@/utils/i18n';
import { ThresholdField } from '@/app/monitor/types';
import { StrategyFields } from '@/app/monitor/types/event';
import { useCommon } from '@/app/monitor/context/common';
import { SCHEDULE_UNIT_MAP, COMPARISON_METHOD } from '@/app/monitor/constants/event';
import {
  COMPARE_MODE_ABSOLUTE,
  COMPARE_MODE_TIMELEFT,
  COUNT_IF_ALGORITHM,
  DEFAULT_FORECAST_LOOKBACK,
  FORECAST_LOOKBACK_OPTIONS,
  defaultCompareValueKind,
  getCompareValueKinds,
  getEnabledCompareModes,
  getMetricThresholdEnumState,
  getThresholdUnitOptions,
  shouldShowThresholdUnitSelector
} from './strategyDetailUtils';
import ThresholdList from './thresholdList';

const { Option } = Select;

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
  isTrap
}) => {
  const { t } = useTranslation();
  const commonContext = useCommon();
  const unitList = commonContext?.unitList || [];

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
    return Promise.resolve();
  };

  const compareModes = useMemo(
    () =>
      getEnabledCompareModes({
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
                  label={
                    <span className="w-[100px]">
                      {t('monitor.events.compareBaseline')}
                    </span>
                  }
                >
                  <div className="flex flex-wrap items-center gap-[10px]">
                    <Select
                      className="w-[220px]"
                      value={compareMode}
                      onChange={handleCompareModeChange}
                    >
                      {compareModes.map((mode) => (
                        <Option key={mode} value={mode}>
                          {compareModeLabels[mode] || mode}
                        </Option>
                      ))}
                    </Select>
                    {compareKindOptions.length > 0 && (
                      <Select
                        className="w-[120px]"
                        value={compareValueKind}
                        onChange={onCompareValueKindChange}
                        aria-label={t('monitor.events.compareValueKind')}
                      >
                        {compareKindOptions.map((kind) => (
                          <Option key={kind} value={kind}>
                            {compareKindLabels[kind] || kind}
                          </Option>
                        ))}
                      </Select>
                    )}
                  </div>
                </Form.Item>
              )}
              {compareMode === COMPARE_MODE_TIMELEFT && !isEnumMetric && (
                <>
                  <Form.Item
                    label={
                      <span className="w-[100px]">
                        {t('monitor.events.forecastTarget')}
                      </span>
                    }
                    required
                  >
                    <InputNumber
                      className="w-[220px]"
                      value={forecastTarget}
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
                      className="w-[220px]"
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
                />
              </Form.Item>

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
                <div className="flex flex-wrap items-center gap-[10px]">
                  <span>{t('monitor.events.recoveryCondition')}</span>
                  <Form.Item
                    name="recovery_condition"
                    noStyle
                    rules={[
                      {
                        required: false,
                        message: t('common.required')
                      }
                    ]}
                  >
                    <InputNumber
                      className="w-[100px]"
                      min={1}
                      precision={0}
                    />
                  </Form.Item>
                  <span>{t('monitor.events.consecutivePeriods')}</span>
                </div>
                <div className="flex flex-wrap items-center gap-[10px] mt-[10px]">
                  <span>{t('monitor.events.recoveryThreshold')}</span>
                  <Select
                    className="w-[80px]"
                    allowClear
                    placeholder={t('monitor.events.recoveryThresholdPlaceholder')}
                    value={recoveryThreshold?.method || undefined}
                    onChange={(method) =>
                      onRecoveryThresholdChange?.({
                        method: method || '',
                        value: recoveryThreshold?.value ?? null
                      })
                    }
                  >
                    {COMPARISON_METHOD.map((item) => (
                      <Option key={item.value} value={item.value}>
                        {item.label}
                      </Option>
                    ))}
                  </Select>
                  <InputNumber
                    className="w-[120px]"
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
                </div>
              </Form.Item>

              {/* 无数据告警 */}
              <Form.Item<StrategyFields>
                name="no_data_level"
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
                <div className="flex flex-wrap items-center">
                  <span>{t('monitor.events.noDataAlertCondition')}</span>
                  <InputNumber
                    className="mx-[10px] w-[80px]"
                    min={SCHEDULE_UNIT_MAP[`${nodataUnit}Min`]}
                    max={SCHEDULE_UNIT_MAP[`${nodataUnit}Max`]}
                    value={noDataAlert}
                    precision={0}
                    onChange={onNoDataAlertChange}
                  />
                  <span className="mr-[10px]">
                    {t('monitor.events.noDataAlertSuffix')}
                  </span>
                  <Select
                    value={noDataAlertLevel}
                    className="w-[180px]"
                    onChange={onNoDataAlertLevelChange}
                  >
                    {NO_DATA_ALERT_OPTIONS.map((item) => (
                      <Option key={item.value} value={item.value}>
                        {t(`monitor.events.${item.labelKey}`)}
                      </Option>
                    ))}
                  </Select>
                </div>
                <div className="flex flex-wrap items-center mt-[10px]">
                  <span>{t('monitor.events.noDataRecoveryWindow')}</span>
                  <InputNumber
                    className="mx-[10px] w-[80px]"
                    min={SCHEDULE_UNIT_MAP[`${noDataRecoveryUnit}Min`]}
                    max={SCHEDULE_UNIT_MAP[`${noDataRecoveryUnit}Max`]}
                    value={noDataRecovery}
                    precision={0}
                    onChange={onNoDataRecoveryChange}
                  />
                  <span>{t('monitor.events.nodataRecover')}</span>
                </div>
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
