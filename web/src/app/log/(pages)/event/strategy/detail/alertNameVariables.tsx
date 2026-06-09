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
    <div className="border border-[var(--color-border-2)] rounded-md p-4">
      <div className="font-medium mb-3">{t('log.event.availableVariables')}</div>
      <div className="space-y-2">
        {variables.map((item) => (
          <div
            key={item.value}
            className="flex items-center justify-between gap-3"
          >
            <span className="text-[var(--color-text-2)] break-all">
              {item.label}
            </span>
            <Button size="small" onClick={() => handleUseVariable(item.value)}>
              {t('log.event.useVariable')}
            </Button>
          </div>
        ))}
      </div>
    </div>
  );
};

export default AlertNameVariables;
