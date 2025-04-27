import React from 'react';
import { Checkbox } from 'antd';
import { useTranslation } from '@/utils/i18n';

interface TableCellsProps {
  record: any;
  activeKey: string;
  activeSubModule: string;
  handleSpecificDataChange: (record: any, module: string, type: string, subModule?: string) => void;
}

export const ActionCell: React.FC<TableCellsProps> = ({
  record,
  activeKey,
  activeSubModule,
  handleSpecificDataChange
}) => {
  const { t } = useTranslation();
  return (
    <div className="flex space-x-4">
      <Checkbox
        checked={record.view}
        onChange={() => handleSpecificDataChange(
          record,
          activeKey,
          'view',
          activeKey === 'provider' ? activeSubModule : undefined
        )}
      >
        {t('system.permission.view')}
      </Checkbox>
      <Checkbox
        checked={record.operate}
        disabled={!record.view}
        onChange={() => handleSpecificDataChange(
          record,
          activeKey,
          'operate',
          activeKey === 'provider' ? activeSubModule : undefined
        )}
      >
        {t('system.permission.operate')}
      </Checkbox>
    </div>
  );
};

export default ActionCell;
