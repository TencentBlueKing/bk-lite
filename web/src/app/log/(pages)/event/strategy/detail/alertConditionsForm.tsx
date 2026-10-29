import React from 'react';
import { Form, Input, Select, InputNumber, Radio, Switch, Tag } from 'antd';
import { useTranslation } from '@/utils/i18n';
import ConditionSelector from './conditionSelector';
import { StrategyFields } from '@/app/log/types/event';
import { FilterItem } from '@/app/log/types/integration';
import { ListItem } from '@/app/log/types';
import { SCHEDULE_UNIT_MAP } from '@/app/log/constants';
import { useScheduleList, useLevelList } from '@/app/log/hooks/event';
import {
  FIXED_SHOW_FIELDS,
  MAX_BACKFILL_COUNT,
  getAlertConditionVisibility,
  getDefaultShowFields,
  hasBackfillGap,
  hasGuardWithAny,
  hasIncompleteCondition,
  hasMismatchedLevelSets,
  hasNoRegularCondition,
  hasNonNumericThreshold,
  hasThresholdOrderError,
} from './policyFormUtils';
import LogQueryInput from '@/app/log/components/log-query-input';

const { Option } = Select;

interface AlertConditionsFormProps {
  policyType?: 'keyword' | 'aggregate';
  unit: string;
  periodUnit: string;
  conditions: FilterItem[];
  term: string | null;
  fieldList: string[];
  fieldListLoading?: boolean;
  logGroups: React.Key[];
  streamList: ListItem[];
  onUnitChange: (val: string) => void;
  onPeriodUnitChange: (val: string) => void;
  onConditionsChange: (val: FilterItem[]) => void;
  onTermChange: (val: string) => void;
}

const AlertConditionsForm: React.FC<AlertConditionsFormProps> = ({
  policyType,
  unit,
  periodUnit,
  conditions,
  term,
  fieldList,
  fieldListLoading = false,
  logGroups,
  streamList,
  onUnitChange,
  onPeriodUnitChange,
  onConditionsChange,
  onTermChange
}) => {
  const { t } = useTranslation();
  const LEVEL_LIST = useLevelList();
  const SCHEDULE_LIST = useScheduleList();
  const lockedPolicyType = policyType || 'keyword';
  const conditionVisibility = getAlertConditionVisibility(lockedPolicyType);
  const schedule = Form.useWatch('schedule');
  const period = Form.useWatch('period');

  // 验证条件函数
  const validateConidtion = async () => {
    if (!term || !conditions.length) {
      return Promise.reject(new Error(t('log.event.ruleValidate')));
    }
    if (hasIncompleteCondition(conditions)) {
      return Promise.reject(new Error(t('log.event.conditionValidate')));
    }
    if (hasNoRegularCondition(conditions)) {
      return Promise.reject(new Error(t('log.event.regularRequired')));
    }
    if (hasGuardWithAny(conditions, term)) {
      return Promise.reject(new Error(t('log.event.guardWithOr')));
    }
    if (hasNonNumericThreshold(conditions)) {
      return Promise.reject(new Error(t('log.event.thresholdNumberValidate')));
    }
    if (hasThresholdOrderError(conditions)) {
      return Promise.reject(new Error(t('log.event.thresholdOrderValidate')));
    }
    if (hasMismatchedLevelSets(conditions, term)) {
      return Promise.reject(new Error(t('log.event.levelSetMismatch')));
    }
    return Promise.resolve();
  };

  return (
    <>
      <Form.Item<StrategyFields> name="alert_type" hidden>
        <Input />
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
            style={{ width: '100%' }}
            showSearch
            mode="multiple"
            maxTagCount="responsive"
            placeholder={t('log.integration.logGroup')}
            options={streamList.map((item: ListItem) => ({
              value: item.id,
              label: item.name
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
          <LogQueryInput
            placeholder={t('common.inputMsg')}
            className="w-full"
            allowClear
            availableFields={fieldList}
            fieldsLoading={fieldListLoading}
            logGroups={logGroups}
            timeRange={{ mode: 'relative', minutes: 15 }}
          />
        </Form.Item>
        <div className="text-[var(--color-text-3)] mt-[10px]">
          {lockedPolicyType === 'aggregate'
            ? t('log.event.aggregateQueryCriteriaTips')
            : t('log.event.queryCriteriaTips')}
        </div>
      </Form.Item>
      {conditionVisibility.showDisplayFields && (
        <Form.Item<StrategyFields>
          required
          label={
            <span className="w-[100px]">{t('log.event.displayFields')}</span>
          }
        >
          <Form.Item
            name="show_fields"
            noStyle
            normalize={(value) => getDefaultShowFields(value)}
            rules={[
              {
                required: true,
                message: t('common.required')
              }
            ]}
          >
            <Select
              style={{ width: '100%' }}
              loading={fieldListLoading}
              showSearch
              mode="multiple"
              maxTagCount="responsive"
              tagRender={(tagProps) => {
                const { label, value, closable, onClose } = tagProps;
                const fixed = (FIXED_SHOW_FIELDS as readonly string[]).includes(String(value));
                return (
                  <Tag closable={fixed ? false : closable} onClose={onClose}>
                    {label}
                  </Tag>
                );
              }}
              options={fieldList
                .filter(
                  (item) =>
                    ![
                      'message',
                      'timestamp',
                      '_time',
                      '_msg',
                      '_stream',
                      '_stream_id',
                      '@timestamp'
                    ].includes(item)
                )
                .map((item) => ({
                  value: item,
                  label: item
                }))}
            />
          </Form.Item>
          <div className="text-[var(--color-text-3)] mt-[10px]">
            {t('log.event.displayFieldsDes')}
          </div>
        </Form.Item>
      )}
      {conditionVisibility.showGroupBy && (
        <Form.Item<StrategyFields>
          label={
            <span className="w-[100px]">{t('log.event.groupByFields')}</span>
          }
        >
          <Form.Item name="group_by" noStyle>
            <Select
              style={{ width: '100%' }}
              loading={fieldListLoading}
              allowClear
              showSearch
              mode="multiple"
              maxTagCount="responsive"
              placeholder={t('log.event.groupByFields')}
            >
              {fieldList.map((item) => (
                <Option key={item} value={item}>
                  {item}
                </Option>
              ))}
            </Select>
          </Form.Item>
          <div className="text-[var(--color-text-3)] mt-[10px]">
            {t('log.event.groupByFieldsDes')}
          </div>
        </Form.Item>
      )}
      {conditionVisibility.showRule && (
        <Form.Item<StrategyFields>
          required
          label={<span className="w-[100px]">{t('log.integration.rule')}</span>}
        >
          <Form.Item
            name="rule"
            noStyle
            // 条件存在父组件 state。这个触发名不会被调用，避免 onChange 把条件写进表单字段 rule。
            // 组校验失败时只在「规则」下展示说明。空状态避免把错误边框铺到卡内每一个输入框。
            trigger="onCollect"
            validateStatus=""
            rules={[
              {
                validator: validateConidtion,
                required: true
              }
            ]}
          >
            <ConditionSelector
              fields={fieldList}
              data={conditions}
              term={term}
              onTermChange={onTermChange}
              onChange={onConditionsChange}
            />
          </Form.Item>
        </Form.Item>
      )}
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
              message: t('common.required')
            }
          ]}
        >
          <InputNumber
            className="w-full"
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
      {lockedPolicyType === 'keyword' ? (
        <Form.Item<StrategyFields>
          label={<span className="w-[100px]">{t('log.event.minHits')}</span>}
        >
          <Form.Item name="min_hits" initialValue={1} noStyle>
            <InputNumber
              data-testid="min-hits"
              min={1}
              max={100000}
              precision={0}
              style={{ width: 160 }}
            />
          </Form.Item>
          <div className="text-[var(--color-text-3)] mt-[10px]">
            {t('log.event.minHitsTip')}
          </div>
        </Form.Item>
      ) : (
        <>
          <Form.Item<StrategyFields>
            label={<span className="w-[100px]">{t('log.event.triggerCount')}</span>}
          >
            <Form.Item name="trigger_count" initialValue={1} noStyle>
              <InputNumber
                data-testid="trigger-count"
                min={1}
                max={5}
                precision={0}
                style={{ width: 120 }}
              />
            </Form.Item>
            <div className="text-[var(--color-text-3)] mt-[10px]">
              {t('log.event.triggerCountTip')}
            </div>
          </Form.Item>
          <Form.Item<StrategyFields>
            label={<span className="w-[100px]">{t('log.event.recoverAfter')}</span>}
          >
            <div className="flex items-center gap-[8px]">
              <Form.Item
                name="recover_enabled"
                valuePropName="checked"
                initialValue
                noStyle
              >
                <Switch data-testid="recover-enabled" />
              </Form.Item>
              <Form.Item noStyle shouldUpdate>
                {({ getFieldValue }) =>
                  getFieldValue('recover_enabled') ? (
                    <Form.Item name="recover_after" initialValue={3} noStyle>
                      <InputNumber
                        data-testid="recover-after"
                        min={1}
                        max={10}
                        precision={0}
                        addonBefore={t('log.event.recoverAfterBefore')}
                        addonAfter={t('log.event.recoverAfterAfter')}
                      />
                    </Form.Item>
                  ) : null
                }
              </Form.Item>
            </div>
            <div className="text-[var(--color-text-3)] mt-[10px]">
              {t('log.event.recoverAfterTip')}
            </div>
          </Form.Item>
        </>
      )}
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
              message: t('common.required')
            }
          ]}
        >
          <InputNumber
            className="w-full"
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
        {hasBackfillGap(schedule, unit, period, periodUnit) ? (
          <div className="mt-1 text-[var(--color-warning)]">
            {t('log.event.backfillGapWarning', undefined, { count: MAX_BACKFILL_COUNT })}
          </div>
        ) : null}
      </Form.Item>
      {lockedPolicyType === 'aggregate' ? null : (
        <Form.Item<StrategyFields>
          name="alert_level"
          label={<span className="w-[100px]">{t('log.event.alarmLevel')}</span>}
          rules={[
            {
              required: true,
              message: t('common.required')
            }
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
      )}
    </>
  );
};

export default AlertConditionsForm;
