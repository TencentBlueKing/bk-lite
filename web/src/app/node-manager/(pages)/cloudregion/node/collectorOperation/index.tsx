'use client';
import React, { useState, useMemo } from 'react';
import { Steps, Result, Button } from 'antd';
import { useTranslation } from '@/utils/i18n';
import OperationProgress, { OperationType } from '../operationProgress';

export interface CollectorOperationProps {
  operationType: OperationType;
  taskId: string;
  collectorId?: string;
  collectorPackageId?: number;
  cancel: () => void;
}

const CollectorOperation: React.FC<CollectorOperationProps> = ({
  operationType,
  taskId,
  collectorId,
  collectorPackageId,
  cancel
}) => {
  const { t } = useTranslation();
  const [currentStep, setCurrentStep] = useState(0);

  // 获取操作类型的显示名称
  const operationName = useMemo(() => {
    const nameMap: Record<string, string> = {
      installCollector: t('node-manager.cloudregion.node.installCollector'),
      startCollector: t('node-manager.cloudregion.node.startCollector'),
      restartCollector: t('node-manager.cloudregion.node.restartCollector'),
      stopCollector: t('node-manager.cloudregion.node.stopCollector'),
      uninstallController: t(
        'node-manager.cloudregion.node.uninstallController'
      )
    };
    return nameMap[operationType] || operationType;
  }, [operationType, t]);

  const handleNextStep = () => {
    setCurrentStep(1);
  };

  // 步骤条配置
  const steps = useMemo(
    () => [
      {
        title: t('node-manager.controller.operationConfig'),
        component: (
          <OperationProgress
            operationType={operationType}
            taskIds={taskId}
            collectorId={collectorId}
            collectorPackageId={collectorPackageId}
            onNext={handleNextStep}
            cancel={cancel}
          />
        )
      },
      {
        title: t('node-manager.controller.operationComplete'),
        component: (
          <Result
            status="success"
            title={t('node-manager.controller.operationCompleteTitle')}
            subTitle={t('node-manager.controller.operationCompleteSubDesc')}
            extra={[
              <Button key="list" type="primary" onClick={cancel}>
                {t('node-manager.controller.viewNodeList')}
              </Button>
            ]}
          />
        )
      }
    ],
    [operationType, taskId, collectorId, collectorPackageId, cancel, t]
  );

  return (
    <div className="w-[calc(100vw-280px)]">
      <div className="w-full">
        <div className="p-[10px]">
          <div className="mb-8 px-[20px]">
            <Steps current={currentStep} size="default">
              <Steps.Step title={operationName} />
              <Steps.Step
                title={t('node-manager.controller.operationComplete')}
              />
            </Steps>
          </div>
          <div>{steps[currentStep].component}</div>
        </div>
      </div>
    </div>
  );
};

export default CollectorOperation;
