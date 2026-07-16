import React from 'react';
import { Alert, Button } from 'antd';
import { SearchOutlined, ToolOutlined } from '@ant-design/icons';
import CodeSnippet from '@/components/code-snippet';
import Icon from '@/components/icon';
import SectionHeader from '@/components/section-header';

export type K8sCollectorVerificationStatus =
  | 'idle'
  | 'waiting'
  | 'success'
  | 'failed';

export interface K8sCollectorInstallProps {
  title: React.ReactNode;
  installDescription: React.ReactNode;
  verifyTitle: React.ReactNode;
  verifyButtonText: React.ReactNode;
  verifyWaitingDescription: React.ReactNode;
  installCommand: string;
  prevButtonText: React.ReactNode;
  successMessage: React.ReactNode;
  successDescription: React.ReactNode;
  failedMessage: React.ReactNode;
  failedDescription: React.ReactNode;
  commonIssuesText?: React.ReactNode;
  installActions?: React.ReactNode;
  verifyDisabled?: boolean;
  isVerifying: boolean;
  verificationStatus: K8sCollectorVerificationStatus;
  onVerify: () => void;
  onPrev: () => void;
  onOpenCommonIssues?: () => void;
}

const K8sCollectorInstall: React.FC<K8sCollectorInstallProps> = ({
  title,
  installDescription,
  verifyTitle,
  verifyButtonText,
  verifyWaitingDescription,
  installCommand,
  prevButtonText,
  successMessage,
  successDescription,
  failedMessage,
  failedDescription,
  commonIssuesText,
  installActions,
  verifyDisabled = false,
  isVerifying,
  verificationStatus,
  onVerify,
  onPrev,
  onOpenCommonIssues,
}) => {
  const showCommonIssuesAction = commonIssuesText && onOpenCommonIssues;

  return (
    <div>
      <div className="mb-[20px]">
        <SectionHeader
          className="mb-[10px]"
          icon={<Icon type="caijiqi" className="text-lg" />}
          title={title}
          actions={showCommonIssuesAction ? (
            <Button icon={<ToolOutlined />} onClick={onOpenCommonIssues}>
              {commonIssuesText}
            </Button>
          ) : null}
        />
        <div className="rounded-md bg-[var(--color-fill-1)] p-[10px]">
          <p className="mb-[6px] text-[12px] text-[var(--color-text-3)]">
            {installDescription}
          </p>
          {installActions ? <div className="mb-[8px]">{installActions}</div> : null}
          <CodeSnippet
            value={installCommand}
            copyable
            tone="inverse"
            maxHeight={120}
            className="min-h-[120px]"
          />
        </div>
      </div>

      <div className="mb-[10px]">
        <SectionHeader
          className="mb-3"
          icon={<Icon type="renzhengyuanguanli" className="text-2xl" />}
          title={verifyTitle}
        />
        <div className="flex items-center gap-4">
          <Button
            type="primary"
            loading={isVerifying}
            icon={<SearchOutlined />}
            disabled={verifyDisabled}
            onClick={onVerify}
          >
            {verifyButtonText}
          </Button>
          <span className="text-[12px] text-[var(--color-text-3)]">
            {verifyWaitingDescription}
          </span>
        </div>
      </div>

      {verificationStatus === 'success' ? (
        <Alert
          message={<b className="text-[var(--color-success)]">{successMessage}</b>}
          description={
            <div className="flex items-center text-[var(--color-success)]">
              <span className="font-medium">{successDescription}</span>
            </div>
          }
          type="success"
          showIcon
        />
      ) : null}

      {verificationStatus === 'failed' ? (
        <Alert
          message={<b className="text-[#faad14]">{failedMessage}</b>}
          description={
            <div className="flex items-center text-[#faad14]">
              <span className="font-medium">{failedDescription}</span>
            </div>
          }
          type="warning"
          showIcon
        />
      ) : null}

      <div className="pt-[20px]">
        <Button onClick={onPrev}>← {prevButtonText}</Button>
      </div>
    </div>
  );
};

export default K8sCollectorInstall;
