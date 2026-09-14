'use client';

import React from 'react';
import { Button, Popover } from 'antd';
import { QuestionCircleOutlined } from '@ant-design/icons';
import { useTranslation } from '@/utils/i18n';
import { operatorTranslation, ruleFields, type RuleScope } from '@/app/alarm/utils/multivalueRules';

const FIELD_GROUPS = [
  ['title', 'description', 'content'],
  ['level'],
  ['source_name', 'source_names'],
  ['push_source_id', 'push_source_ids'],
  ['resource_type', 'resource_id'],
  ['resource_name', 'item', 'service', 'location'],
];

interface MatchRuleHelpProps { scope: RuleScope }

const MatchRuleHelp = ({ scope }: MatchRuleHelpProps) => {
  const { t } = useTranslation();
  const fields = ruleFields(scope);
  const alertScope = scope === 'assignment' || scope === 'action';
  const descriptions = [
    'textInput', 'levelInput', alertScope ? 'alertSourceInput' : 'eventSourceInput',
    alertScope ? 'alertMonitorInput' : 'eventMonitorInput', 'identityInput', 'mixedInput',
  ];
  const content = <div className="max-h-[40vh] w-[min(620px,calc(100vw-48px))] overflow-y-auto text-xs leading-5 text-[var(--color-text-1)]">
    <p className="mb-3">{t('alarmCommon.ruleHelp.groups')}</p>
    <table className="w-full border-collapse text-left">
      <thead className="bg-[var(--color-bg-4)]">
        <tr>
          <th scope="col" className="w-28 px-3 py-2 font-medium">{t('alarmCommon.ruleHelp.field')}</th>
          <th scope="col" className="px-3 py-2 font-medium">{t('alarmCommon.ruleHelp.matching')}</th>
        </tr>
      </thead>
      <tbody>
        {FIELD_GROUPS.map((keys, index) => {
          const group = fields.filter(field => keys.includes(field.key));
          if (!group.length) return null;
          return <tr key={keys[0]} className="border-b border-[var(--color-border-1)]">
            <th scope="row" className="px-3 py-2 align-top font-normal">
              {group.map(field => t(`alarmCommon.ruleFields.${field.key}`)).join(' / ')}
            </th>
            <td className="px-3 py-2 align-top">
              <div>{group[0].operators.map(operator => t(operatorTranslation(group[0].key, operator))).join(' / ')}</div>
              <div className="mt-1 text-[var(--color-text-3)]">{t(`alarmCommon.ruleHelp.${descriptions[index]}`)}</div>
            </td>
          </tr>;
        })}
      </tbody>
    </table>
    <div className="mt-3 space-y-2 text-[var(--color-text-2)]">
      <p className="mb-0">{t('alarmCommon.ruleHelp.textMeaning')}</p>
      <p className="mb-0">{t('alarmCommon.ruleHelp.candidateMeaning')}</p>
      {alertScope && <p className="mb-0">{t('alarmCommon.ruleHelp.setExample')}</p>}
      <p className="mb-0">{t('alarmCommon.ruleHelp.empty')}</p>
      <p className="mb-0">{t('alarmCommon.ruleHelp.tags')}</p>
    </div>
  </div>;

  return <Popover title={t('alarmCommon.ruleHelp.title')} content={content} trigger={['hover', 'click']} placement="bottomLeft">
    <Button type="text" size="small" icon={<QuestionCircleOutlined />} className="text-xs text-[var(--color-text-3)]"
      aria-label={t('alarmCommon.ruleHelp.title')}>
      {t('alarmCommon.ruleHelp.title')}
    </Button>
  </Popover>;
};

export default MatchRuleHelp;
