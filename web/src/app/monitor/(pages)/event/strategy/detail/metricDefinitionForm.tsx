import React from 'react';
import {
  Form,
  Input,
  Button,
  Segmented,
  Select,
  Tooltip,
  InputNumber,
} from 'antd';
import { PlusOutlined } from '@ant-design/icons';
import { useTranslation } from '@/utils/i18n';
import { SegmentedItem, IndexViewItem, FilterItem } from '@/app/monitor/types';
import { SourceFeild, StrategyFields } from '@/app/monitor/types/event';
import { useScheduleList, useMethodList } from '@/app/monitor/hooks/event';
import { SCHEDULE_UNIT_MAP } from '@/app/monitor/constants/event';
import ConditionSelector from './conditionSelector';
import strategyStyle from '../index.module.scss';

const { Option } = Select;
const { TextArea } = Input;

interface MetricDefinitionFormProps {
  pluginList: SegmentedItem[];
  source: SourceFeild;
  metric: string | null;
  metricsLoading: boolean;
  labels: string[];
  conditions: FilterItem[];
  groupBy: string[];
  unit: string;
  periodUnit: string;
  originMetricData: IndexViewItem[];
  monitorName: string;
  onCollectTypeChange: (id: string) => void;
  onOpenInstModal: () => void;
  onMetricChange: (val: string) => void;
  onFiltersChange: (filters: FilterItem[]) => void;
  onGroupChange: (val: string[]) => void;
  onUnitChange: (val: string) => void;
  onPeriodUnitChange: (val: string) => void;
  isTrap: (getFieldValue: any) => boolean;
}

const MetricDefinitionForm: React.FC<MetricDefinitionFormProps> = ({
  pluginList,
  source,
  metric,
  metricsLoading,
  labels,
  conditions,
  groupBy,
  unit,
  periodUnit,
  originMetricData,
  monitorName,
  onCollectTypeChange,
  onOpenInstModal,
  onMetricChange,
  onFiltersChange,
  onGroupChange,
  onUnitChange,
  onPeriodUnitChange,
  isTrap,
}) => {
  const { t } = useTranslation();
  // 在组件内部引入hooks，减少props传递
  const METHOD_LIST = useMethodList();
  const SCHEDULE_LIST = useScheduleList();

  // 验证函数移到组件内部
  const validateAssets = async () => {
    if (!source.values.length) {
      return Promise.reject(new Error(t('monitor.assetValidate')));
    }
    return Promise.resolve();
  };

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
        className={strategyStyle.clusterLabel}
        name="collect_type"
        label={<span className={strategyStyle.label}></span>}
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
            <>
              <Form.Item<StrategyFields>
                label={<span className="w-[100px]">{t('monitor.source')}</span>}
                name="source"
                rules={[{ required: true, validator: validateAssets }]}
              >
                <div>
                  <div className="flex">
                    {t('common.select')}
                    <span className="text-[var(--color-primary)] px-[4px]">
                      {source.values.length}
                    </span>
                    {t('monitor.assets')}
                    <Button
                      className="ml-[10px]"
                      icon={<PlusOutlined />}
                      size="small"
                      onClick={onOpenInstModal}
                    ></Button>
                  </div>
                  <div className="text-[var(--color-text-3)] mt-[10px]">
                    {t('monitor.events.setAssets')}
                  </div>
                </div>
              </Form.Item>
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
            </>
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
                <span className="w-[100px]">{t('monitor.events.method')}</span>
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
                  placeholder={t('monitor.events.method')}
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
          <span className="w-[100px]">{t('monitor.events.frequency')}</span>
        }
      >
        <Form.Item
          name="schedule"
          noStyle
          rules={[
            {
              required: true,
              message: t('common.required'),
            },
          ]}
        >
          <InputNumber
            min={SCHEDULE_UNIT_MAP[`${unit}Min`]}
            max={SCHEDULE_UNIT_MAP[`${unit}Max`]}
            precision={0}
            addonAfter={
              <Select
                value={unit}
                style={{ width: 120 }}
                onChange={onUnitChange}
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
          {t('monitor.events.setFrequency')}
        </div>
      </Form.Item>
      <Form.Item<StrategyFields>
        required
        label={<span className="w-[100px]">{t('monitor.events.period')}</span>}
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
