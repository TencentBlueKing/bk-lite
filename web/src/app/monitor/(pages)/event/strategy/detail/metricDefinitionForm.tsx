import React from 'react';
import { Form, Input, Segmented, Select, Tooltip, InputNumber } from 'antd';
import { useTranslation } from '@/utils/i18n';
import { SegmentedItem, IndexViewItem, FilterItem } from '@/app/monitor/types';
import { StrategyFields } from '@/app/monitor/types/event';
import { useScheduleList, useMethodList } from '@/app/monitor/hooks/event';
import { SCHEDULE_UNIT_MAP } from '@/app/monitor/constants/event';
import ConditionSelector from './conditionSelector';

const { Option } = Select;
const { TextArea } = Input;

interface MetricDefinitionFormProps {
  pluginList: SegmentedItem[];
  metric: string | null;
  metricsLoading: boolean;
  labels: string[];
  conditions: FilterItem[];
  groupBy: string[];
  periodUnit: string;
  originMetricData: IndexViewItem[];
  monitorName: string;
  onCollectTypeChange: (id: string) => void;
  onMetricChange: (val: string) => void;
  onFiltersChange: (filters: FilterItem[]) => void;
  onGroupChange: (val: string[]) => void;
  onPeriodUnitChange: (val: string) => void;
  isTrap: (getFieldValue: any) => boolean;
}

const MetricDefinitionForm: React.FC<MetricDefinitionFormProps> = ({
  pluginList,
  metric,
  metricsLoading,
  labels,
  conditions,
  groupBy,
  periodUnit,
  originMetricData,
  monitorName,
  onCollectTypeChange,
  onMetricChange,
  onFiltersChange,
  onGroupChange,
  onPeriodUnitChange,
  isTrap,
}) => {
  const { t } = useTranslation();
  // 在组件内部引入hooks，减少props传递
  const METHOD_LIST = useMethodList();
  const SCHEDULE_LIST = useScheduleList();

  // 验证函数移到组件内部
  const validateMetric = async () => {
    if (!metric) {
      return Promise.reject(new Error(t('monitor.events.metricValidate')));
    }
    if (
      conditions.length &&
      conditions.some((item) => {
        return Object.values(item).some((tex) => !tex);
      })
    ) {
      return Promise.reject(new Error(t('monitor.events.conditionValidate')));
    }
    return Promise.resolve();
  };

  return (
    <>
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
                  message: t('common.required'),
                },
              ]}
            >
              <TextArea
                placeholder={t('monitor.events.promQLPlaceholder')}
                className="w-[800px]"
                allowClear
                rows={4}
              />
            </Form.Item>
          ) : (
            <Form.Item<StrategyFields>
              name="metric"
              label={<span className="w-[100px]">{t('monitor.metric')}</span>}
              rules={[{ validator: validateMetric, required: true }]}
            >
              <ConditionSelector
                data={{
                  metric,
                  filters: conditions,
                  group: groupBy,
                }}
                metricData={originMetricData}
                labels={labels}
                loading={metricsLoading}
                monitorName={monitorName}
                onMetricChange={onMetricChange}
                onFiltersChange={onFiltersChange}
                onGroupChange={onGroupChange}
              />
              <div className="text-[var(--color-text-3)]">
                {t('monitor.events.setDimensions')}
              </div>
            </Form.Item>
          )
        }
      </Form.Item>
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
                    message: t('common.required'),
                  },
                ]}
              >
                <Select
                  style={{
                    width: '300px',
                  }}
                  placeholder={t('monitor.events.convergenceMethod')}
                  showSearch
                >
                  {METHOD_LIST.map((item) => (
                    <Option value={item.value} key={item.value}>
                      <Tooltip
                        overlayInnerStyle={{
                          whiteSpace: 'pre-line',
                          color: 'var(--color-text-1)',
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
                {t('monitor.events.setMethod')}
              </div>
            </Form.Item>
          )
        }
      </Form.Item>
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
              message: t('common.required'),
            },
          ]}
        >
          <InputNumber
            min={SCHEDULE_UNIT_MAP[`${periodUnit}Min`]}
            max={SCHEDULE_UNIT_MAP[`${periodUnit}Max`]}
            precision={0}
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
          {t('monitor.events.setPeriod')}
        </div>
      </Form.Item>
    </>
  );
};

export default MetricDefinitionForm;
