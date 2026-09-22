import React, { useEffect, useCallback, useMemo } from 'react';
import {
  Form,
  Input,
  Select,
  Tooltip,
  InputNumber,
  FormInstance
} from 'antd';
import { useTranslation } from '@/utils/i18n';
import {
  SegmentedItem,
  IndexViewItem,
  CascaderItem,
  UnitListItem
} from '@/app/monitor/types';
import { StrategyFields } from '@/app/monitor/types/event';
import {
  useScheduleList,
  useMethodList,
  useGroupMethodList
} from '@/app/monitor/hooks/event';
import { COMPARISON_METHOD, SCHEDULE_UNIT_MAP } from '@/app/monitor/constants/event';
import { useConditionList } from '@/app/monitor/hooks';
import { useObjectConfigInfo } from '@/app/monitor/hooks/integration/common/getObjectConfig';
import { debounce } from 'lodash';
import { sanitizeGroupBy } from '@/app/monitor/utils/metricDimensions';
import MetricExpressionEditor from './metricExpressionEditor';
import { MetricExpressionRow } from './metricExpressionTypes';
import {
  buildMetricExpressionQueryCondition,
  MetricExpressionMode
} from './formulaExpressionUtils';
import {
  COUNT_IF_ALGORITHM,
  NEW_ALGORITHMS,
  PER_SERIES_ALGORITHMS,
  formatAlgorithmDisplayLabel,
  getAlgorithmShortName,
  groupAlgorithmOptions
} from './strategyDetailUtils';

const { Option } = Select;
const { TextArea } = Input;
const defaultGroup = ['instance_id'];

interface MetricDefinitionFormProps {
  form: FormInstance<StrategyFields>;
  pluginList: SegmentedItem[];
  metricsLoading: boolean;
  period: number | null;
  periodUnit: string;
  originMetricData: IndexViewItem[];
  monitorName: string;
  metricRows: MetricExpressionRow[];
  metricExpressionMode: MetricExpressionMode;
  resultName: string;
  expression: string;
  resultUnit: string | null;
  labelsByRef: Record<string, string[]>;
  groupedUnitOptions: CascaderItem[];
  unitList: UnitListItem[];
  onCollectTypeChange: (id: string | number) => void;
  onMetricRowsChange: (rows: MetricExpressionRow[]) => void;
  onResultNameChange: (value: string) => void;
  onExpressionChange: (value: string) => void;
  onResultUnitChange: (value: string) => void;
  onPeriodChange: (val: number | null) => void;
  onPeriodUnitChange: (val: string) => void;
  onAlgorithmChange: (val: string) => void;
  isEnumMetric?: boolean;
  disableRateAlgorithm?: boolean;
  countPredicate?: { method: string; value: number | null };
  onCountPredicateChange?: (val: { method: string; value: number | null }) => void;
  isTrap: (getFieldValue: any) => boolean;
}

const MetricDefinitionForm: React.FC<MetricDefinitionFormProps> = ({
  form,
  pluginList,
  metricsLoading,
  periodUnit,
  originMetricData,
  monitorName,
  metricRows,
  metricExpressionMode,
  resultName,
  expression,
  resultUnit,
  labelsByRef,
  groupedUnitOptions,
  unitList,
  onCollectTypeChange,
  onMetricRowsChange,
  onResultNameChange,
  onExpressionChange,
  onResultUnitChange,
  onPeriodChange,
  onPeriodUnitChange,
  onAlgorithmChange,
  isEnumMetric = false,
  disableRateAlgorithm = false,
  countPredicate,
  onCountPredicateChange,
  isTrap
}) => {
  const { t } = useTranslation();
  const METHOD_LIST = useMethodList();
  const algorithmOptions = useMemo(() => {
    return METHOD_LIST.filter((item) => {
      const value = String(item.value);
      if (isEnumMetric && NEW_ALGORITHMS.includes(value)) {
        return false;
      }
      if (
        metricExpressionMode === 'formula' &&
        PER_SERIES_ALGORITHMS.includes(value)
      ) {
        return false;
      }
      return true;
    }).map((item) => ({
      ...item,
      disabled: disableRateAlgorithm && String(item.value) === 'rate'
    }));
  }, [METHOD_LIST, isEnumMetric, metricExpressionMode, disableRateAlgorithm]);
  const groupedAlgorithmOptions = useMemo(
    () => groupAlgorithmOptions(algorithmOptions),
    [algorithmOptions]
  );
  const GROUP_METHOD_LIST = useGroupMethodList();
  const SCHEDULE_LIST = useScheduleList();
  const CONDITION_LIST = useConditionList();
  const { getGroupIds } = useObjectConfigInfo(monitorName);

  // 固定维度作为每个指标行的基础选项，指标标签由编辑器按行补充。
  const groupByOptions = useMemo(() => {
    return sanitizeGroupBy(getGroupIds(monitorName)?.list || defaultGroup);
  }, [monitorName, getGroupIds]);

  // 防抖处理汇聚周期值变化
  const debouncedPeriodChange = useCallback(
    debounce((val: number | null) => {
      onPeriodChange(val);
    }, 500),
    [onPeriodChange]
  );

  // 处理汇聚周期输入变化
  const handlePeriodInputChange = (val: number | null) => {
    form.setFieldValue('period', val);
    debouncedPeriodChange(val);
  };

  // 同步外部状态到 Form，使验证能正常工作
  useEffect(() => {
    form.setFieldsValue({
      metric: metricRows.map((row) => `${row.ref}:${row.metricId || ''}`).join('|')
    });
  }, [metricRows, form]);

  // 验证指标
  const validateMetric = async () => {
    try {
      buildMetricExpressionQueryCondition({
        mode: metricExpressionMode,
        resultName,
        expression,
        rows: metricRows
      });
      return Promise.resolve();
    } catch (error) {
      return Promise.reject(
        new Error(
          error instanceof Error
            ? error.message
            : t('monitor.events.metricValidate')
        )
      );
    }
  };

  return (
    <>
      {pluginList.length > 1 && (
        <Form.Item
          name="collect_type"
          label={
            <span className="w-[100px]">
              {t('monitor.events.collectionTemplate')}
            </span>
          }
          rules={[{ required: true, message: t('common.required') }]}
        >
          <Select
            style={{ width: '100%' }}
            placeholder={t('monitor.events.collectionTemplate')}
            showSearch
            allowClear={false}
            options={pluginList}
            filterOption={(input, option) =>
              String(option?.label || '')
                .toLowerCase()
                .includes(input.toLowerCase())
            }
            onChange={onCollectTypeChange}
          />
        </Form.Item>
      )}
      <Form.Item
        noStyle
        shouldUpdate={(prevValues, currentValues) =>
          prevValues.collect_type !== currentValues.collect_type
        }
      >
        {({ getFieldValue }) =>
          isTrap(getFieldValue) ? (
            <Form.Item<StrategyFields>
              label={<span className="w-[100px]">PromQL</span>}
              name="query"
              rules={[
                {
                  required: true,
                  message: t('common.required')
                }
              ]}
            >
              <TextArea
                placeholder={t('monitor.events.promQLPlaceholder')}
                className="w-full"
                allowClear
                rows={4}
              />
            </Form.Item>
          ) : (
            <>
              {/* 指标 */}
              <Form.Item<StrategyFields>
                name="metric"
                label={<span className="w-[100px]">{t('monitor.metric')}</span>}
                rules={[{ validator: validateMetric, required: true }]}
                className="mb-[16px]"
              >
                <MetricExpressionEditor
                  id="basic_metric"
                  rows={metricRows}
                  mode={metricExpressionMode}
                  resultName={resultName}
                  expression={expression}
                  resultUnit={resultUnit}
                  labelsByRef={labelsByRef}
                  originMetricData={originMetricData}
                  groupByOptions={groupByOptions}
                  groupMethods={GROUP_METHOD_LIST}
                  conditionMethods={CONDITION_LIST}
                  metricsLoading={metricsLoading}
                  groupedUnitOptions={groupedUnitOptions}
                  unitList={unitList}
                  onRowsChange={onMetricRowsChange}
                  onResultNameChange={onResultNameChange}
                  onExpressionChange={onExpressionChange}
                  onResultUnitChange={onResultUnitChange}
                />
              </Form.Item>
            </>
          )
        }
      </Form.Item>

      {/* 汇聚周期 - 移到汇聚方式之前 */}
      <Form.Item<StrategyFields>
        required
        label={
          <span className="w-[100px]">
            {t('monitor.events.convergenceCycle')}
          </span>
        }
      >
        <Form.Item
          name="period"
          noStyle
          rules={[
            {
              required: true,
              message: t('common.required')
            }
          ]}
        >
          <InputNumber
            className="w-full"
            min={SCHEDULE_UNIT_MAP[`${periodUnit}Min`]}
            max={SCHEDULE_UNIT_MAP[`${periodUnit}Max`]}
            precision={0}
            onChange={handlePeriodInputChange}
            addonAfter={
              <Select
                value={periodUnit}
                style={{ width: 120 }}
                onChange={onPeriodUnitChange}
              >
                {SCHEDULE_LIST.map((item) => (
                  <Option key={item.value} value={item.value}>
                    {item.label}
                  </Option>
                ))}
              </Select>
            }
          />
        </Form.Item>
        <div className="text-[var(--color-text-3)] mt-[10px]">
          {t('monitor.events.convergenceCycleTip')}
        </div>
      </Form.Item>

      {/* 汇聚方式 - 移到汇聚周期之后 */}
      <Form.Item
        noStyle
        shouldUpdate={(prevValues, currentValues) =>
          prevValues.collect_type !== currentValues.collect_type
        }
      >
        {({ getFieldValue }) =>
          isTrap(getFieldValue) ? null : (
            <Form.Item<StrategyFields>
              required
              label={
                <span className="w-[100px]">
                  {t('monitor.events.convergenceMethod')}
                </span>
              }
            >
              <Form.Item
                name="algorithm"
                noStyle
                rules={[
                  {
                    required: true,
                    message: t('common.required')
                  },
                  {
                    validator: async (_, value) => {
                      if (disableRateAlgorithm && value === 'rate') {
                        return Promise.reject(
                          new Error(t('monitor.events.rateAlreadyInQuery'))
                        );
                      }
                      return Promise.resolve();
                    }
                  }
                ]}
              >
                <Select
                  style={{
                    width: '100%'
                  }}
                  placeholder={t('monitor.events.convergenceMethod')}
                  showSearch
                  optionFilterProp="label"
                  filterOption={(input, option) => {
                    const query = input.trim().toLowerCase();
                    if (!query) return true;
                    const label = String(option?.label || '').toLowerCase();
                    const value = String(option?.value || '').toLowerCase();
                    const shortName = getAlgorithmShortName(
                      String(option?.value || '')
                    ).toLowerCase();
                    return (
                      label.includes(query) ||
                      value.includes(query) ||
                      shortName.includes(query)
                    );
                  }}
                  onChange={onAlgorithmChange}
                >
                  {groupedAlgorithmOptions.map((group) => (
                    <Select.OptGroup
                      key={group.key}
                      label={
                        group.key === 'change'
                          ? t('monitor.events.algorithmGroupChange')
                          : t('monitor.events.algorithmGroupWindow')
                      }
                    >
                      {group.options.map((item) => {
                        const shortName = getAlgorithmShortName(
                          String(item.value)
                        );
                        const showShort =
                          Boolean(shortName) &&
                          shortName !==
                            String(item.label).trim().toUpperCase();
                        return (
                        <Option
                          value={item.value}
                          key={item.value}
                          disabled={item.disabled}
                          label={formatAlgorithmDisplayLabel(
                            String(item.label),
                            String(item.value)
                          )}
                        >
                          <Tooltip
                            overlayInnerStyle={{ whiteSpace: 'pre-line' }}
                            placement="right"
                            title={
                              item.disabled
                                ? t('monitor.events.rateAlreadyInQuery')
                                : item.title
                            }
                          >
                            <span className="flex w-full min-w-0 items-center">
                              <span className="shrink-0 text-[var(--color-text-1)]">
                                {item.label}
                              </span>
                              {showShort ? (
                                <span className="text-[var(--color-text-3)]">
                                  （{shortName}）
                                </span>
                              ) : null}
                            </span>
                          </Tooltip>
                        </Option>
                        );
                      })}
                    </Select.OptGroup>
                  ))}
                </Select>
              </Form.Item>
              <div className="text-[var(--color-text-3)] mt-[10px]">
                {t('monitor.events.convergenceMethodTip')}
              </div>
            </Form.Item>
          )
        }
      </Form.Item>
      <Form.Item
        noStyle
        shouldUpdate={(prevValues, currentValues) =>
          prevValues.algorithm !== currentValues.algorithm ||
          prevValues.collect_type !== currentValues.collect_type
        }
      >
        {({ getFieldValue }) =>
          isTrap(getFieldValue) ||
          getFieldValue('algorithm') !== COUNT_IF_ALGORITHM ? null : (
            <Form.Item
              label={
                <span className="w-[100px]">
                  {t('monitor.events.countPredicate')}
                </span>
              }
              required
            >
              <InputNumber
                className="w-full"
                addonBefore={
                  <Select
                    value={countPredicate?.method || '>'}
                    popupMatchSelectWidth={false}
                    style={{ width: 80 }}
                    aria-label={t('monitor.events.method')}
                    onChange={(method) =>
                      onCountPredicateChange?.({
                        method,
                        value: countPredicate?.value ?? null
                      })
                    }
                  >
                    {COMPARISON_METHOD.map((item) => (
                      <Option value={item.value} key={String(item.value)}>
                        {item.label}
                      </Option>
                    ))}
                  </Select>
                }
                value={countPredicate?.value}
                placeholder={t('common.inputTip')}
                onChange={(value) =>
                  onCountPredicateChange?.({
                    method: countPredicate?.method || '>',
                    value: typeof value === 'number' ? value : null
                  })
                }
              />
            </Form.Item>
          )
        }
      </Form.Item>
    </>
  );
};

export default MetricDefinitionForm;
