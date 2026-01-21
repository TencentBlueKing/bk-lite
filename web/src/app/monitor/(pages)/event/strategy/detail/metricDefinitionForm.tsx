import React, { useEffect } from 'react';
import {
  Form,
  Input,
  Segmented,
  Select,
  Tooltip,
  InputNumber,
  Button,
  FormInstance,
} from 'antd';
import { PlusOutlined, CloseOutlined } from '@ant-design/icons';
import { useTranslation } from '@/utils/i18n';
import {
  SegmentedItem,
  IndexViewItem,
  FilterItem,
  MetricItem,
  ListItem,
} from '@/app/monitor/types';
import { StrategyFields } from '@/app/monitor/types/event';
import { useScheduleList, useMethodList } from '@/app/monitor/hooks/event';
import { SCHEDULE_UNIT_MAP } from '@/app/monitor/constants/event';
import { useConditionList } from '@/app/monitor/hooks';
import { useObjectConfigInfo } from '@/app/monitor/hooks/integration/common/getObjectConfig';
import strategyStyle from '../index.module.scss';

const { Option } = Select;
const { TextArea } = Input;
const defaultGroup = ['instance_id'];

interface MetricDefinitionFormProps {
  form: FormInstance<StrategyFields>;
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
  form,
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
  const METHOD_LIST = useMethodList();
  const SCHEDULE_LIST = useScheduleList();
  const CONDITION_LIST = useConditionList();
  const { getGroupIds } = useObjectConfigInfo();

  // 同步外部状态到 Form，使验证能正常工作
  useEffect(() => {
    form.setFieldsValue({ metric: metric || undefined });
  }, [metric, form]);

  useEffect(() => {
    // 当 conditions 变化时，触发条件维度字段的重新验证
    if (conditions.length) {
      form.validateFields(['_conditions_validator']).catch(() => {
        // 忽略验证错误，只是为了更新验证状态
      });
    }
  }, [conditions, form]);

  // 验证指标
  const validateMetric = async () => {
    if (!metric) {
      return Promise.reject(new Error(t('monitor.events.metricValidate')));
    }
    return Promise.resolve();
  };

  // 验证条件维度（如果有条件但未填写完整则报错）
  const validateConditions = async () => {
    if (
      conditions.length &&
      conditions.some((item) => {
        return Object.values(item).some((tex) => !tex);
      })
    ) {
      return Promise.reject(
        new Error(t('monitor.events.conditionFieldValidate'))
      );
    }
    return Promise.resolve();
  };

  // 条件维度操作函数
  const handleLabelChange = (value: string, index: number) => {
    const newConditions = [...conditions];
    newConditions[index].name = value;
    onFiltersChange(newConditions);
  };

  const handleConditionChange = (value: string, index: number) => {
    const newConditions = [...conditions];
    newConditions[index].method = value;
    onFiltersChange(newConditions);
  };

  const handleValueChange = (
    e: React.ChangeEvent<HTMLInputElement>,
    index: number
  ) => {
    const newConditions = [...conditions];
    newConditions[index].value = e.target.value;
    onFiltersChange(newConditions);
  };

  const addConditionItem = () => {
    onFiltersChange([...conditions, { name: null, method: null, value: '' }]);
  };

  const deleteConditionItem = (index: number) => {
    onFiltersChange(conditions.filter((_, i) => i !== index));
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
                  message: t('common.required'),
                },
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
                <Select
                  allowClear
                  style={{ width: '100%' }}
                  placeholder={t('monitor.metric')}
                  showSearch
                  value={metric}
                  loading={metricsLoading}
                  filterOption={(input, option) =>
                    (option?.label || '')
                      .toLowerCase()
                      .includes(input.toLowerCase())
                  }
                  options={originMetricData.map((item) => ({
                    label: item.display_name,
                    title: item.name,
                    options: (item.child || []).map((tex: MetricItem) => ({
                      label: tex.display_name,
                      value: tex.name,
                    })),
                  }))}
                  onChange={onMetricChange}
                />
              </Form.Item>

              {/* 分组维度 */}
              <Form.Item
                label={
                  <span className="w-[100px]">
                    {t('monitor.events.groupDimension')}
                  </span>
                }
                className="mb-[16px]"
              >
                <Select
                  style={{ width: '100%' }}
                  showSearch
                  allowClear
                  mode="multiple"
                  maxTagCount="responsive"
                  placeholder={t('monitor.events.groupDimension')}
                  value={groupBy}
                  onChange={onGroupChange}
                >
                  {(getGroupIds(monitorName)?.list || defaultGroup).map(
                    (item: string) => (
                      <Option value={item} key={item}>
                        {item}
                      </Option>
                    )
                  )}
                </Select>
                <div className="text-[var(--color-text-3)] mt-[8px]">
                  {t('monitor.events.groupDimensionTip')}
                </div>
              </Form.Item>

              {/* 条件维度 */}
              <Form.Item
                name="_conditions_validator"
                label={
                  <span className="w-[100px]">
                    {t('monitor.events.conditionDimension')}
                  </span>
                }
                className="mb-[16px]"
                rules={[{ validator: validateConditions }]}
              >
                <div className={strategyStyle.condition}>
                  <div className={strategyStyle.conditionItem}>
                    {conditions.length ? (
                      <ul className={strategyStyle.conditions}>
                        {conditions.map((conditionItem, index) => (
                          <li
                            className={`${strategyStyle.itemOption} ${strategyStyle.filter}`}
                            key={index}
                          >
                            <Select
                              className={strategyStyle.filterLabel}
                              placeholder={t('monitor.label')}
                              showSearch
                              value={conditionItem.name}
                              onChange={(val) => handleLabelChange(val, index)}
                            >
                              {labels.map((item: string) => (
                                <Option value={item} key={item}>
                                  {item}
                                </Option>
                              ))}
                            </Select>
                            <Select
                              style={{ width: '100px' }}
                              placeholder={t('monitor.term')}
                              value={conditionItem.method}
                              onChange={(val) =>
                                handleConditionChange(val, index)
                              }
                            >
                              {CONDITION_LIST.map((item: ListItem) => (
                                <Option value={item.id} key={item.id}>
                                  {item.name}
                                </Option>
                              ))}
                            </Select>
                            <Input
                              style={{ width: '150px' }}
                              placeholder={t('monitor.value')}
                              value={conditionItem.value}
                              onChange={(e) => handleValueChange(e, index)}
                            />
                            <Button
                              icon={<CloseOutlined />}
                              onClick={() => deleteConditionItem(index)}
                            />
                            <Button
                              icon={<PlusOutlined />}
                              onClick={addConditionItem}
                            />
                          </li>
                        ))}
                      </ul>
                    ) : (
                      <div className="flex items-center">
                        <Button
                          disabled={!metric}
                          icon={<PlusOutlined />}
                          onClick={addConditionItem}
                        />
                      </div>
                    )}
                  </div>
                </div>
                <div className="text-[var(--color-text-3)] mt-[8px]">
                  {t('monitor.events.conditionDimensionTip')}
                </div>
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
                    message: t('common.required'),
                  },
                ]}
              >
                <Select
                  style={{
                    width: '100%',
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
