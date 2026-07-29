import React, { useEffect, useState } from 'react';
import { Button, message } from 'antd';
import K8sCommonIssuesDrawer from '@/app/monitor/components/k8s-common-issues-drawer';
import type { K8sCommonIssuesPreset } from '@/app/monitor/components/k8s-common-issues-drawer/presets';
import K8sCollectorInstall, {
  K8sCollectorVerificationStatus,
} from '@/app/monitor/components/k8s-collector-install';

export interface K8sCollectorInstallStepCopy {
  title: React.ReactNode;
  installDescription: React.ReactNode;
  verifyTitle: React.ReactNode;
  verifyButtonText: React.ReactNode;
  verifyWaitingDescription: React.ReactNode;
  prevButtonText: React.ReactNode;
  successMessage: React.ReactNode;
  successDescription: React.ReactNode;
  failedMessage: React.ReactNode;
  failedDescription: React.ReactNode;
  commonIssuesText?: React.ReactNode;
  troubleshootText?: React.ReactNode;
  verifyFailedToast: string;
}

interface K8sCollectorInstallStepProps {
  installCommand: string;
  copy: K8sCollectorInstallStepCopy;
  onVerifyStatus: () => Promise<boolean>;
  onPrev: () => void;
  onNext: () => void;
  onOpenCommonIssues?: () => void;
  commonIssuesPreset?: K8sCommonIssuesPreset;
  installActions?: React.ReactNode;
  verifyDisabled?: boolean;
  initialVerificationStatus?: K8sCollectorVerificationStatus;
  successDelayMs?: number;
}

const K8sCollectorInstallStep: React.FC<K8sCollectorInstallStepProps> = ({
  installCommand,
  copy,
  onVerifyStatus,
  onPrev,
  onNext,
  onOpenCommonIssues,
  commonIssuesPreset,
  installActions,
  verifyDisabled = false,
  initialVerificationStatus,
  successDelayMs = 1500,
}) => {
  const [isVerifying, setIsVerifying] = useState(false);
  const [commonIssuesOpen, setCommonIssuesOpen] = useState(false);
  const [verificationStatus, setVerificationStatus] =
    useState<K8sCollectorVerificationStatus>(
      initialVerificationStatus ?? (installCommand ? 'waiting' : 'idle')
    );

  useEffect(() => {
    if (installCommand && verificationStatus === 'idle') {
      setVerificationStatus('waiting');
    }
  }, [installCommand, verificationStatus]);

  const handleVerify = async () => {
    try {
      setIsVerifying(true);
      const success = await onVerifyStatus();

      if (success) {
        setVerificationStatus('success');
        setTimeout(() => {
          onNext();
        }, successDelayMs);
        return;
      }

      setVerificationStatus('failed');
      message.warning(copy.verifyFailedToast);
    } finally {
      setIsVerifying(false);
    }
  };

  const handleOpenCommonIssues = () => {
    if (commonIssuesPreset) {
      setCommonIssuesOpen(true);
      return;
    }
    onOpenCommonIssues?.();
  };

  return (
    <>
      <K8sCollectorInstall
        title={copy.title}
        installDescription={copy.installDescription}
        verifyTitle={copy.verifyTitle}
        verifyButtonText={copy.verifyButtonText}
        verifyWaitingDescription={copy.verifyWaitingDescription}
        installCommand={installCommand}
        installActions={installActions}
        prevButtonText={copy.prevButtonText}
        successMessage={copy.successMessage}
        successDescription={copy.successDescription}
        failedMessage={copy.failedMessage}
        failedDescription={
          <>
            {copy.failedDescription}
            {copy.commonIssuesText &&
            (commonIssuesPreset || onOpenCommonIssues) ? (
              <>
                {' '}
                <Button
                  type="link"
                  className="p-[0]"
                  onClick={handleOpenCommonIssues}
                >
                  {copy.commonIssuesText}
                </Button>{' '}
                {copy.troubleshootText}
              </>
              ) : null}
          </>
        }
        commonIssuesText={copy.commonIssuesText}
        verifyDisabled={verifyDisabled}
        isVerifying={isVerifying}
        verificationStatus={verificationStatus}
        onVerify={handleVerify}
        onPrev={onPrev}
        onOpenCommonIssues={
          commonIssuesPreset || onOpenCommonIssues
            ? handleOpenCommonIssues
            : undefined
        }
      />
      {commonIssuesPreset ? (
        <K8sCommonIssuesDrawer
          title={commonIssuesPreset.title}
          issues={commonIssuesPreset.issues}
          reasonLabel={commonIssuesPreset.reasonLabel}
          solutionLabel={commonIssuesPreset.solutionLabel}
          open={commonIssuesOpen}
          onOpenChange={setCommonIssuesOpen}
        />
      ) : null}
    </>
  );
};

export default K8sCollectorInstallStep;
export {
  createCmdbK8sCollectorInstallCopy,
  createLogK8sCollectorInstallCopy,
  createMonitorK8sCollectorInstallCopy,
} from './presets';
