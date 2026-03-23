'use client';
import React from 'react';
import { InstallingProps } from '@/app/node-manager/types/controller';
import OperationProgress from '@/app/node-manager/(pages)/cloudregion/node/operationProgress';

const Installing: React.FC<InstallingProps> = ({
  onNext,
  cancel,
  installData
}) => {
  return (
    <OperationProgress
      operationType="installController"
      taskIds={installData?.taskIds || ''}
      installMethod={installData?.installMethod}
      manualTaskList={installData?.manualTaskList || []}
      onNext={onNext}
      cancel={cancel}
    />
  );
};

export default Installing;
