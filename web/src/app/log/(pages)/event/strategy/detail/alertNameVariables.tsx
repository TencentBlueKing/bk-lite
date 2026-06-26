import React from 'react';
import { Button, FormInstance } from 'antd';
import type { ColumnsType } from 'antd/es/table';
import { useTranslation } from '@/utils/i18n';
import CustomTable from '@/components/custom-table';
import {
  buildAlertNameVariables,
  insertAlertNameVariable
} from './policyFormUtils';
import strategyStyle from '../index.module.scss';

interface AlertNameVariablesProps {
  form: FormInstance;
  groupBy?: string[];
}

interface VariableItem {
  label: string;
  value: string;
  description: string;
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

  const columns: ColumnsType<VariableItem> = [
    {
      title: t('log.event.variableName'),
      dataIndex: 'label',
      key: 'label',
      width: '45%',
      render: (text: string) => (
        <span className={strategyStyle.variableValue}>{text}</span>
      )
    },
    {
      title: t('common.description'),
      dataIndex: 'description',
      key: 'description',
      render: (description: string) =>
        t(
          description === 'alertLevel'
            ? 'log.event.alertLevelVariable'
            : 'log.event.groupFieldVariable'
        )
    },
    {
      title: t('common.action'),
      key: 'action',
      width: 80,
      render: (_: unknown, record: VariableItem) => (
        <Button
          type="link"
          size="small"
          onClick={() => handleUseVariable(record.value)}
        >
          {t('log.event.useVariable')}
        </Button>
      )
    }
  ];

  return (
    <div
      className={`${strategyStyle.previewCard} ${strategyStyle.previewCardPadded} ${strategyStyle.variableCard} ${strategyStyle.variableTable}`}
    >
      <div className={strategyStyle.variableCardHeader}>
        <span>{t('log.event.availableVariables')}</span>
        <span className={strategyStyle.variableHint}>
          {t('log.event.variableUsageTips')}
        </span>
      </div>
      <CustomTable
        autoScrollX={false}
        columns={columns}
        dataSource={variables}
        pagination={false}
        size="small"
        rowKey="value"
      />
    </div>
  );
};

export default AlertNameVariables;
