'use client';
import React from 'react';
import { InstallingProps } from '@/app/node-manager/types/controller';
import OperationProgress from '@/app/node-manager/(pages)/cloudregion/node/operationProgress';
import { BULK_INSTALL_METHOD } from '../installConfig/bulkInstall';
import BulkInstallProgress from './bulkInstallProgress';

const Installing: React.FC<InstallingProps> = ({
  onNext,
  cancel,
  installData
}) => {
  if (installData?.installMethod === BULK_INSTALL_METHOD) {
    return (
      <BulkInstallProgress
        batchId={installData?.bulkBatchId}
        onFinish={cancel}
      />
    );
  }

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
