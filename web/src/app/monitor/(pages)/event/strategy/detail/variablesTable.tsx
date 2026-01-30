'use client';
import React, { useMemo } from 'react';
import { Button } from 'antd';
import type { ColumnsType } from 'antd/es/table';
import { useTranslation } from '@/utils/i18n';
import CustomTable from '@/components/custom-table';

interface VariableItem {
  key: string;
  variable: string;
  description: string;
}

interface VariablesTableProps {
  onVariableSelect?: (variable: string) => void;
}

const VariablesTable: React.FC<VariablesTableProps> = ({
  onVariableSelect
}) => {
  const { t } = useTranslation();

  // 可选变量数据
  const variableData: VariableItem[] = useMemo(
    () => [
      {
        key: 'monitor_object',
        variable: '${monitor_object}',
        description: t('monitor.events.variableMonitorObject')
      },
      {
        key: 'instance_name',
        variable: '${instance_name}',
        description: t('monitor.events.variableInstanceName')
      },
      {
        key: 'level',
        variable: '${level}',
        description: t('monitor.events.variableLevel')
      },
      {
        key: 'metric_name',
        variable: '${metric_name}',
        description: t('monitor.events.variableMetricName')
      },
      {
        key: 'value',
        variable: '${value}',
        description: t('monitor.events.variableValue')
      },
      {
        key: 'instance_id',
        variable: '${instance_id}',
        description: t('monitor.events.variableInstanceId')
      }
    ],
    [t]
  );

  const variableColumns: ColumnsType<VariableItem> = [
    {
      title: t('monitor.events.variableName'),
      dataIndex: 'variable',
      key: 'variable',
      render: (text: string) => (
        <span className="text-[var(--color-primary)] font-mono">{text}</span>
      )
    },
    {
      title: t('common.description'),
      dataIndex: 'description',
      key: 'description'
    },
    {
      title: t('common.actions'),
      key: 'action',
      fixed: 'right',
      width: 80,
      render: (_: unknown, record: VariableItem) => (
        <Button
          type="link"
          size="small"
          onClick={() => onVariableSelect?.(record.variable)}
        >
          {t('monitor.events.useVariable')}
        </Button>
      )
    }
  ];

  return (
    <div className="w-full border border-[var(--color-border-2)] rounded-md p-4 bg-[var(--color-bg-1)] shadow-md mb-4">
      <div className="font-medium text-[14px] mb-3">
        {t('monitor.events.optionalVariables')}
      </div>
      <CustomTable
        scroll={{ x: 'max-content' }}
        columns={variableColumns}
        dataSource={variableData}
        pagination={false}
        size="small"
        rowKey="key"
      />
    </div>
  );
};

export default VariablesTable;
