'use client';

import React, { useState, useEffect } from 'react';
import { useTranslation } from '@/utils/i18n';
import { Select, Button, Input } from 'antd';
import { DeleteOutlined, PlusOutlined, MinusCircleOutlined } from '@ant-design/icons';
import { useCommon } from '@/app/alarm/context/common';
import { type RuleScope, type RuleCondition, ruleFields, ruleField, operatorTranslation, invalidRuleCondition, isMultiOperator, normalizeRuleTags } from '@/app/alarm/utils/multivalueRules';
import { MatchRuleValue } from './matchRuleValue';
import MatchRuleHelp from './matchRuleHelp';

interface PolicyItem { key: string | undefined; operator: string | undefined; value: MatchRuleValue }
export interface MatchRuleProps {
  scope?: RuleScope;
  value?: PolicyItem[][];
  onChange?: (val: PolicyItem[][]) => void;
  levelType?: 'alert' | 'event' | 'incident';
  monitorSourceField?: 'push_source_ids' | 'push_source_id';
}
const emptyCondition = (): PolicyItem => ({ key: undefined, operator: undefined, value: undefined });

const RulesMatch: React.FC<MatchRuleProps> = ({ value, onChange, scope: suppliedScope, levelType = 'event', monitorSourceField }) => {
  const scope = suppliedScope || (monitorSourceField === 'push_source_ids' ? 'assignment' : 'enrichment');
  const { levelMeta } = useCommon();
  const { t } = useTranslation();
  const [policyList, setPolicyList] = useState<PolicyItem[][]>(value?.length ? value : [[emptyCondition()]]);
  const levelOptions = levelMeta[levelType]?.list || [];
  const publish = (next: PolicyItem[][]) => { setPolicyList(next); onChange?.(next); };
  const change = (groupIndex: number, conditionIndex: number, update: Partial<RuleCondition>) =>
    publish(policyList.map((group, g) => group.map((condition, c) => g === groupIndex && c === conditionIndex ? { ...condition, ...update } : condition)));

  useEffect(() => { setPolicyList(value?.length ? value : [[emptyCondition()]]); }, [value]);


  return <div className="w-full min-w-0 space-y-3">
    {policyList.map((group, groupIndex) => <React.Fragment key={groupIndex}>
      {groupIndex > 0 && <div className="flex items-center gap-3 text-xs text-[var(--color-text-3)]">
        <span className="h-px flex-1 bg-[var(--color-border-1)]" />{t('common.or')}<span className="h-px flex-1 bg-[var(--color-border-1)]" />
      </div>}
      <div className="rounded-lg border border-[var(--color-border-1)] bg-[var(--color-bg-4)] p-3">
        <div className="mb-3 flex min-h-6 items-center justify-between gap-2">
          <div className="flex flex-wrap items-center gap-1">
            <span className="text-xs text-[var(--color-text-3)]">{t('alarmCommon.allRuleConditions')}</span>
            <MatchRuleHelp scope={scope} />
          </div>
          {policyList.length > 1 && <Button type="text" size="small" icon={<DeleteOutlined />} aria-label={t('alarmCommon.removeRuleGroup')}
            onClick={() => publish(policyList.filter((_, index) => index !== groupIndex))} />}
        </div>
        <div className="space-y-3">
          {group.map((condition, conditionIndex) => {
            const field = ruleField(condition.key, scope);
            const operatorValid = !!field && (field.operators as readonly string[]).includes(condition.operator || '');
            const invalid = invalidRuleCondition(condition, scope);
            const updateValue = (value: MatchRuleValue) => change(groupIndex, conditionIndex, { value });
            const enabled = !!field && operatorValid;
            const multi = isMultiOperator(condition.operator);
            const missing = condition.value === undefined || condition.value === '' || (Array.isArray(condition.value) && !condition.value.length);
            return <div key={conditionIndex}>
              <div className="flex flex-wrap items-start gap-2">
                <div className="w-36 shrink-0">
                  <Select className="w-full" popupMatchSelectWidth={220} allowClear value={field?.key}
                    status={condition.key && !field ? 'error' : undefined} placeholder={t('common.selectTip')}
                    options={ruleFields(scope).map(item => ({ value: item.key, label: t(`alarmCommon.ruleFields.${item.key}`) }))}
                    onChange={key => change(groupIndex, conditionIndex, { key, operator: undefined, value: undefined })} />
                </div>
                <div className="w-48 shrink-0">
                  <Select className="w-full" popupMatchSelectWidth={260} allowClear disabled={!field}
                    value={operatorValid ? condition.operator : undefined} status={condition.operator && !operatorValid ? 'error' : undefined}
                    placeholder={t('common.selectTip')} options={(field?.operators || []).map(operator => ({ value: operator, label: t(operatorTranslation(field?.key, operator)) }))}
                    onChange={operator => change(groupIndex, conditionIndex, { operator, value: isMultiOperator(operator) === multi ? condition.value : undefined })} />
                </div>
                <div className="min-w-[180px] flex-1">
                  {field?.options === 'level' ? <Select<string[]> className="w-full" mode="multiple" showSearch allowClear optionFilterProp="label"
                    disabled={!enabled} value={Array.isArray(condition.value) ? condition.value.filter((v): v is string => typeof v === 'string') : []}
                    placeholder={t('common.selectTip')} status={invalid && !missing ? 'error' : undefined}
                    options={levelOptions.map(level => ({ value: String(level.level_id), label: level.level_display_name }))}
                    onChange={updateValue} />
                  : multi ? <Select className="w-full" mode="tags" open={false} suffixIcon={null} options={[]} aria-label={t('alarmCommon.multiValueInput')}
                    disabled={!enabled} value={Array.isArray(condition.value) ? condition.value.filter((v): v is string => typeof v === 'string') : []}
                    maxCount={50} maxLength={256} placeholder={t('alarmCommon.multiValuePlaceholder')}
                    status={invalid && !missing ? 'error' : undefined}
                    onChange={values => updateValue(normalizeRuleTags(values))} />
                  : <Input disabled={!enabled} value={typeof condition.value === 'string' ? condition.value : ''}
                      maxLength={256} placeholder={t('common.inputTip')} status={invalid && !missing ? 'error' : undefined}
                      onChange={event => updateValue(event.target.value)} />}
                </div>
                <Button type="text" className="shrink-0" icon={<MinusCircleOutlined />} disabled={group.length === 1}
                  aria-label={t('alarmCommon.removeRuleCondition')}
                  onClick={() => publish(policyList.map((item, index) => index === groupIndex ? item.filter((_, index) => index !== conditionIndex) : item))} />
              </div>
              {((condition.key && !field) || (condition.operator && !operatorValid) || (!missing && invalid)) &&
                <p role="alert" className="mb-0 mt-2 text-xs text-[var(--color-fail)]">{t('alarmCommon.invalidRuleCondition')}</p>}
              {multi && operatorValid && <p className="mb-0 mt-2 text-xs leading-5 text-[var(--color-text-3)]">{t(`alarmCommon.multiHints.${condition.operator}${field?.type === 'list' && condition.operator === 'any_of' ? 'List' : ''}`)}</p>}
            </div>;
          })}
        </div>
        <Button type="link" size="small" className="mt-3 px-0" icon={<PlusOutlined aria-hidden />}
          onClick={() => publish(policyList.map((item, index) => index === groupIndex ? [...item, emptyCondition()] : item))}>{t('alarmCommon.addRuleCondition')}</Button>
      </div>
    </React.Fragment>)}
    <Button type="dashed" block icon={<PlusOutlined aria-hidden />} onClick={() => publish([...policyList, [emptyCondition()]])}>{t('alarmCommon.addRuleGroup')}</Button>
  </div>;
};
export default RulesMatch;
