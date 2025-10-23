import React from 'react';
import { Form, Input, Select, InputNumber, Radio } from 'antd';
import { useTranslation } from '@/utils/i18n';
import { useTermList } from '@/app/log/hooks/integration/common/other';
import ConditionSelector from './conditionSelector';
import SelectCard from './selectCard';
import { StrategyFields } from '@/app/log/types/event';
import { FilterItem } from '@/app/log/types/integration';
import { ListItem } from '@/app/log/types';
import { SCHEDULE_UNIT_MAP } from '@/app/log/constants';
import {
  useAlgorithmList,
  useScheduleList,
  useLevelList,
} from '@/app/log/hooks/event';

const { Option } = Select;

interface AlertConditionsFormProps {
  unit: string;
  periodUnit: string;
  conditions: FilterItem[];
  term: string | null;
  fieldList: string[];
  streamList: ListItem[];
  onUnitChange: (val: string) => void;
  onPeriodUnitChange: (val: string) => void;
  onConditionsChange: (val: FilterItem[]) => void;
  onTermChange: (val: string) => void;
}

const AlertConditionsForm: React.FC<AlertConditionsFormProps> = ({
  unit,
  periodUnit,
  conditions,
  term,
  fieldList,
  streamList,
  onUnitChange,
  onPeriodUnitChange,
  onConditionsChange,
  onTermChange,
}) => {
  const { t } = useTranslation();
  const LEVEL_LIST = useLevelList();
  const SCHEDULE_LIST = useScheduleList();
  const ALGORITHM_LIST = useAlgorithmList();
  const TERM_LIST = useTermList();

  // 验证条件函数
  const validateConidtion = async () => {
    if (!term || !conditions.length) {
      return Promise.reject(new Error(t('log.event.ruleValidate')));
    }
    if (
      conditions.length &&
      conditions.some((item) => {
        return Object.values(item).some((tex) => !tex);
      })
    ) {
      return Promise.reject(new Error(t('log.event.conditionValidate')));
    }
    return Promise.resolve();
  };

  return (
    <>
      <Form.Item<StrategyFields>
        name="alert_type"
        label={<span className="w-[100px]">{t('log.event.algorithm')}</span>}
        rules={[{ required: true, message: t('common.required') }]}
      >
        <SelectCard data={ALGORITHM_LIST} />
      </Form.Item>
      <Form.Item<StrategyFields>
        required
        label={<span className="w-[100px]">{t('log.event.alertName')}</span>}
        shouldUpdate={(prevValues, currentValues) =>
          prevValues.alert_type !== currentValues.alert_type
        }
      >
        {({ getFieldValue }) => (
          <>
            <Form.Item
              name="alert_name"
              noStyle
              rules={[
                {
                  required: true,
                  message: t('common.required'),
                },
              ]}
            >
              <Input
                placeholder={t('log.event.alertName')}
                className="w-[800px]"
              />
            </Form.Item>
            <div className="text-[var(--color-text-3)] mt-[10px]">
              {getFieldValue('alert_type') === 'aggregate'
                ? t('log.event.alertNameTitle')
                : t('log.event.keyWordAlertNameTitle')}
            </div>
          </>
        )}
      </Form.Item>
      <Form.Item<StrategyFields>
        required
        label={
          <span className="w-[100px]">{t('log.integration.logGroup')}</span>
        }
      >
        <Form.Item
          name="log_groups"
          noStyle
          rules={[{ required: true, message: t('common.required') }]}
        >
          <Select
            style={{ width: 800 }}
            showSearch
            mode="multiple"
            maxTagCount="responsive"
            placeholder={t('log.integration.logGroup')}
            options={streamList.map((item: ListItem) => ({
              value: item.id,
              label: item.name,
            }))}
          ></Select>
        </Form.Item>
        <div className="text-[var(--color-text-3)] mt-[10px]">
          {t('log.integration.logGroupTips')}
        </div>
      </Form.Item>
      <Form.Item<StrategyFields>
        required
        label={
          <span className="w-[100px]">{t('log.event.queryCriteria')}</span>
        }
      >
        <Form.Item
          name="query"
          noStyle
          rules={[{ required: true, message: t('common.required') }]}
        >
          <Input
            placeholder={t('common.inputMsg')}
            className="w-[800px]"
            allowClear
          />
        </Form.Item>
        <div className="text-[var(--color-text-3)] mt-[10px]">
          {t('log.event.queryCriteriaTips')}
        </div>
      </Form.Item>
      <Form.Item
        noStyle
        shouldUpdate={(prevValues, currentValues) =>
          prevValues.alert_type !== currentValues.alert_type
        }
      >
        {({ getFieldValue }) =>
          getFieldValue('alert_type') === 'aggregate' ? (
            <>
              <Form.Item<StrategyFields>
                required
                label={
                  <span className="w-[100px]">
                    {t('log.event.polymerizationConditions')}
                  </span>
                }
              >
                <Form.Item
                  name="group_by"
                  noStyle
                  rules={[
                    {
                      required: true,
                      message: t('common.required'),
                    },
                  ]}
                >
                  <Select
                    style={{ width: 800 }}
                    allowClear
                    showSearch
                    mode="multiple"
                    maxTagCount="responsive"
                  >
                    {fieldList.map((item) => (
                      <Option key={item} value={item}>
                        {item}
                      </Option>
                    ))}
                  </Select>
                </Form.Item>
                <div className="text-[var(--color-text-3)] mt-[10px]">
                  {t('log.event.polymerizationConditionsDes')}
                </div>
              </Form.Item>
              <Form.Item<StrategyFields>
                required
                label={
                  <span className="w-[100px]">{t('log.integration.rule')}</span>
                }
              >
                <Form.Item
                  name="rule"
                  noStyle
                  rules={[
                    {
                      validator: validateConidtion,
                      required: true,
                    },
                  ]}
                >
                  <div className="flex items-center mb-[20px] w-[800px]">
                    <span>{t('log.integration.meetRule')}</span>
                    <Select
                      className="ml-[8px] flex-1"
                      placeholder={t('log.integration.rule')}
                      showSearch
                      value={term}
                      onChange={onTermChange}
                    >
                      {TERM_LIST.map((item: ListItem) => (
                        <Option value={item.value} key={item.value}>
                          {item.name}
                        </Option>
                      ))}
                    </Select>
                  </div>
                  <ConditionSelector
                    fields={fieldList}
                    data={conditions}
                    onChange={onConditionsChange}
                  ></ConditionSelector>
                </Form.Item>
              </Form.Item>
            </>
          ) : (
            <Form.Item<StrategyFields>
              required
              label={
                <span className="w-[100px]">
                  {t('log.event.displayFields')}
                </span>
              }
            >
              <Form.Item
                name="show_fields"
                noStyle
                rules={[
                  {
                    required: true,
                    message: t('common.required'),
                  },
                ]}
              >
                <Select
                  style={{ width: 800 }}
                  showSearch
                  mode="multiple"
                  maxTagCount="responsive"
                  options={fieldList
                    .filter(
                      (item) =>
                        !['message', 'timestamp', '_time', '_msg'].includes(
                          item
                        )
                    )
                    .map((item) => ({
                      value: item,
                      label: item,
                    }))}
                />
              </Form.Item>
              <div className="text-[var(--color-text-3)] mt-[10px]">
                {t('log.event.displayFieldsDes')}
              </div>
            </Form.Item>
          )
        }
      </Form.Item>
      <Form.Item<StrategyFields>
        required
        label={<span className="w-[100px]">{t('log.event.frequency')}</span>}
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
          {t('log.event.setFrequency')}
        </div>
      </Form.Item>
      <Form.Item<StrategyFields>
        required
        label={<span className="w-[100px]">{t('log.event.period')}</span>}
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
          {t('log.event.setPeriod')}
        </div>
      </Form.Item>
      <Form.Item<StrategyFields>
        name="alert_level"
        label={<span className="w-[100px]">{t('log.event.alarmLevel')}</span>}
        rules={[
          {
            required: true,
            message: t('common.required'),
          },
        ]}
      >
        <Radio.Group>
          {LEVEL_LIST.map((item) => (
            <Radio key={item.value} value={item.value}>
              {item.label}
            </Radio>
          ))}
        </Radio.Group>
      </Form.Item>
    </>
  );
};

export default AlertConditionsForm;
