import React from 'react';
import { Form, Radio } from 'antd';
import type { FormInstance } from 'antd';

type AlarmRuleScopeValue = 'all' | 'filter';

interface AlarmRuleScopeFieldProps {
  form: FormInstance;
  label: React.ReactNode;
  allLabel: React.ReactNode;
  filterLabel: React.ReactNode;
  requiredMessage: string;
  matchRuleNode: React.ReactNode;
  scopeValue?: AlarmRuleScopeValue;
  onScopeChange?: (value: AlarmRuleScopeValue) => void;
  matchTypeFieldName?: string;
  matchRulesFieldName?: string;
  labelTooltip?: React.ReactNode;
  radioVariant?: 'default' | 'button';
  validateMatchRules?: boolean;
  matchRulesClassName?: string;
  radioGroupClassName?: string;
  levelOffsetStyle?: React.CSSProperties;
}

const defaultLevelOffsetStyle: React.CSSProperties = {
  marginLeft: '110px',
  marginTop: '-10px',
  marginBottom: '26px'
};

const AlarmRuleScopeField: React.FC<AlarmRuleScopeFieldProps> = ({
  form,
  label,
  allLabel,
  filterLabel,
  requiredMessage,
  matchRuleNode,
  scopeValue,
  onScopeChange,
  matchTypeFieldName = 'match_type',
  matchRulesFieldName = 'match_rules',
  labelTooltip,
  radioVariant = 'default',
  validateMatchRules = true,
  matchRulesClassName,
  radioGroupClassName = 'mt-1',
  levelOffsetStyle = defaultLevelOffsetStyle
}) => {
  const watchedRuleType = Form.useWatch(matchTypeFieldName, form);
  const resolvedRuleType = scopeValue ?? watchedRuleType ?? 'all';

  const radioGroup = (
    <Radio.Group
      className={radioGroupClassName}
      value={resolvedRuleType}
      onChange={(event) => onScopeChange?.(event.target.value)}
    >
      {radioVariant === 'button' ? (
        <>
          <Radio.Button value="all">{allLabel}</Radio.Button>
          <Radio.Button value="filter">{filterLabel}</Radio.Button>
        </>
      ) : (
        <>
          <Radio value="all">{allLabel}</Radio>
          <Radio value="filter">{filterLabel}</Radio>
        </>
      )}
    </Radio.Group>
  );

  return (
    <>
      {scopeValue === undefined ? (
        <Form.Item
          initialValue="all"
          name={matchTypeFieldName}
          label={label}
          tooltip={labelTooltip}
          rules={[{ required: true, message: requiredMessage }]}
        >
          {radioGroup}
        </Form.Item>
      ) : (
        <Form.Item label={label} tooltip={labelTooltip} className={matchRulesClassName}>
          {radioGroup}
        </Form.Item>
      )}

      {resolvedRuleType === 'filter' && (
        <Form.Item
          name={matchRulesFieldName}
          validateTrigger={[]}
          className={matchRulesClassName}
          style={levelOffsetStyle}
          rules={
            validateMatchRules
              ? [
                {
                  validator: (_, value: any[][]) => {
                    if (!Array.isArray(value) || value.length === 0) {
                      return Promise.reject(new Error(requiredMessage));
                    }
                    for (const orGroup of value) {
                      if (!Array.isArray(orGroup) || orGroup.length === 0) {
                        return Promise.reject(new Error(requiredMessage));
                      }
                      for (const item of orGroup) {
                        if (
                          !item.key ||
                          !item.operator ||
                          (!item.value && item.value !== 0)
                        ) {
                          return Promise.reject(new Error(requiredMessage));
                        }
                      }
                    }
                    return Promise.resolve();
                  }
                }
              ]
              : undefined
          }
        >
          {matchRuleNode}
        </Form.Item>
      )}
    </>
  );
};

export default AlarmRuleScopeField;
