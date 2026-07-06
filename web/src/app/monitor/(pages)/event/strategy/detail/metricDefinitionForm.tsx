import React, { useEffect, useCallback, useMemo } from 'react';
import {
  Form,
  Input,
  Segmented,
  Select,
  Tooltip,
  InputNumber,
  FormInstance
} from 'antd';
import { useTranslation } from '@/utils/i18n';
import { SegmentedItem, IndexViewItem } from '@/app/monitor/types';
import { StrategyFields } from '@/app/monitor/types/event';
import {
  useScheduleList,
  useMethodList,
  useGroupMethodList
} from '@/app/monitor/hooks/event';
import { SCHEDULE_UNIT_MAP } from '@/app/monitor/constants/event';
import { useConditionList } from '@/app/monitor/hooks';
import { useObjectConfigInfo } from '@/app/monitor/hooks/integration/common/getObjectConfig';
import { debounce } from 'lodash';
import { sanitizeGroupBy } from '@/app/monitor/utils/metricDimensions';
import MetricExpressionEditor from './metricExpressionEditor';
import { MetricExpressionRow } from './metricExpressionTypes';
import { buildMetricExpressionQueryCondition } from './formulaExpressionUtils';

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
  resultName: string;
  expression: string;
  labelsByRef: Record<string, string[]>;
  onCollectTypeChange: (id: string) => void;
  onMetricRowsChange: (rows: MetricExpressionRow[]) => void;
  onResultNameChange: (value: string) => void;
  onExpressionChange: (value: string) => void;
  onPeriodChange: (val: number | null) => void;
  onPeriodUnitChange: (val: string) => void;
  onAlgorithmChange: (val: string) => void;
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
  resultName,
  expression,
  labelsByRef,
  onCollectTypeChange,
  onMetricRowsChange,
  onResultNameChange,
  onExpressionChange,
  onPeriodChange,
  onPeriodUnitChange,
  onAlgorithmChange,
  isTrap
}) => {
  const { t } = useTranslation();
  const METHOD_LIST = useMethodList();
  const GROUP_METHOD_LIST = useGroupMethodList();
  const SCHEDULE_LIST = useScheduleList();
  const CONDITION_LIST = useConditionList();
  const { getGroupIds } = useObjectConfigInfo();

  // 固定维度作为每个指标行的基础选项，指标标签由编辑器按行补充。
  const groupByOptions = useMemo(() => {
    return sanitizeGroupBy(getGroupIds(monitorName)?.list || defaultGroup);
  }, [monitorName, getGroupIds]);

  // 防抖处理汇聚周期值变化
  // eslint-disable-next-line react-hooks/exhaustive-deps
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
          <Segmented
            className="custom-tabs"
            options={pluginList}
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
                  rows={metricRows}
                  resultName={resultName}
                  expression={expression}
                  labelsByRef={labelsByRef}
                  originMetricData={originMetricData}
                  groupByOptions={groupByOptions}
                  groupMethods={GROUP_METHOD_LIST}
                  conditionMethods={CONDITION_LIST}
                  metricsLoading={metricsLoading}
                  onRowsChange={onMetricRowsChange}
                  onResultNameChange={onResultNameChange}
                  onExpressionChange={onExpressionChange}
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
                  }
                ]}
              >
                <Select
                  style={{
                    width: '100%'
                  }}
                  placeholder={t('monitor.events.convergenceMethod')}
                  showSearch
                  onChange={onAlgorithmChange}
                >
                  {METHOD_LIST.map((item) => (
                    <Option value={item.value} key={item.value}>
                      <Tooltip
                        overlayInnerStyle={{
                          whiteSpace: 'pre-line',
                          color: 'var(--color-text-1)'
                        }}
                        placement="rightTop"
                        arrow={false}
                        color="var(--color-bg-1)"
                        title={item.title}
                      >
                        <span className="w-full flex">{item.label}</span>
                      </Tooltip>
                    </Option>
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
    </>
  );
};

export default MetricDefinitionForm;
