import React from 'react';
import { Button, FormInstance } from 'antd';
import { useTranslation } from '@/utils/i18n';
import {
  buildAlertNameVariables,
  insertAlertNameVariable
} from './policyFormUtils';

interface AlertNameVariablesProps {
  form: FormInstance;
  groupBy?: string[];
}

const AlertNameVariables: React.FC<AlertNameVariablesProps> = ({
  form,
  groupBy
}) => {
  const { t } = useTranslation();
  const variables = buildAlertNameVariables(groupBy);

  const handleUseVariable = (variable: string) => {
    const currentValue = form.getFieldValue('alert_name') || '';
    form.setFieldsValue({
      alert_name: insertAlertNameVariable(currentValue, variable)
    });
  };

  return (
    <div className="border border-[var(--color-border-2)] rounded-md bg-[var(--color-bg-1)] overflow-hidden">
      <div className="font-medium px-4 py-3 border-b border-[var(--color-border-2)]">
        {t('log.event.availableVariables')}
      </div>
      <div className="px-4 py-3 text-[var(--color-text-3)] border-b border-[var(--color-border-2)]">
        {t('log.event.variableUsageTips')}
      </div>
      <div className="grid grid-cols-[1fr_120px_70px] bg-[var(--color-fill-1)] px-4 py-2 font-medium">
        <span>{t('log.event.variableName')}</span>
        <span>{t('common.description')}</span>
        <span>{t('common.action')}</span>
      </div>
      <div>
        {variables.map((item) => (
          <div
            key={item.value}
            className="grid grid-cols-[1fr_120px_70px] items-center px-4 py-3 border-t border-[var(--color-border-1)]"
          >
            <span className="text-[var(--color-text-2)] break-all font-mono">
              {item.label}
            </span>
            <span>
              {t(
                item.description === 'alertLevel'
                  ? 'log.event.alertLevelVariable'
                  : 'log.event.groupFieldVariable'
              )}
            </span>
            <Button type="link" size="small" onClick={() => handleUseVariable(item.value)}>
              {t('log.event.useVariable')}
            </Button>
          </div>
        ))}
      </div>
    </div>
  );
};

export default AlertNameVariables;
