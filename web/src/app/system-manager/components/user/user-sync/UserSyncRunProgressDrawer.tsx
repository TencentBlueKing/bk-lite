import React from 'react';
import {
  CheckCircleFilled,
  ClockCircleFilled,
  CloseCircleFilled,
  LoadingOutlined,
  ReloadOutlined,
} from '@ant-design/icons';
import { Alert, Button, Drawer, Empty, Progress, Skeleton, Steps, Tag, Typography } from 'antd';

import type { UserSyncRun, UserSyncRunProgressPayload } from '@/app/system-manager/types/user-sync';
import { RUN_STATUS_TEXT_STYLE } from '@/app/system-manager/utils/userSyncPageUtils';
import {
  calcPercent,
  formatEmailNotificationResult,
  formatElapsed,
  formatPhaseErrorMessage,
  formatPhaseBusinessResult,
  formatPhaseCounterLine,
  formatPhaseProgressMeta,
  getPhaseLabel,
  getPhaseDisplayProgress,
  getPhaseDisplayStatus,
  getPhaseStatusConfig,
  getPhasesForRun,
  safeGetPhaseProgress,
  shouldExpandPhase,
} from '@/app/system-manager/utils/userSyncProgress';
import { useLocalizedTime } from '@/hooks/useLocalizedTime';

import styles from './UserSyncRunProgressDrawer.module.scss';

export interface UserSyncRunProgressDrawerProps {
  open: boolean;
  run: UserSyncRun | null;
  loading: boolean;
  t: (key: string, fallback?: string) => string;
  onRefresh: () => void;
  onClose: () => void;
}

const phaseIcon: Record<string, React.ReactNode> = {
  check: <CheckCircleFilled className={styles.successIcon} />,
  loading: <LoadingOutlined spin className={styles.runningIcon} />,
  clock: <ClockCircleFilled className={styles.mutedIcon} />,
  close: <CloseCircleFilled className={styles.errorIcon} />,
  minus: <ClockCircleFilled className={styles.mutedIcon} />,
};

const UserSyncRunProgressDrawer: React.FC<UserSyncRunProgressDrawerProps> = ({
  open,
  run,
  loading,
  t,
  onRefresh,
  onClose,
}) => {
  const { convertToLocalizedTime } = useLocalizedTime();
  const payload = (run?.payload ?? {}) as UserSyncRunProgressPayload;
  const phases = getPhasesForRun(payload);
  const currentStepIndex = Math.max(
    0,
    phases.findIndex((phase) => {
      const entry = safeGetPhaseProgress(payload, phase);
      const status = getPhaseDisplayStatus(phase, entry, payload);
      return status === 'wait' || status === 'process';
    }),
  );
  const statusColor = run ? RUN_STATUS_TEXT_STYLE[run.status] : 'default';
  const headerTitle = run?.source_name ?? t('system.user.userSyncPage.progressDrawer.title');

  return (
    <Drawer
      className={styles.drawer}
      width={700}
      title={
        <div className={styles.headerLine}>
          <span className={styles.headerTitle}>{headerTitle}</span>
          {run && (
            <>
              <Tag bordered={false} color={statusColor}>
                {t(`system.user.userSyncPage.runStatus.${run.status}`)}
              </Tag>
              {run.finished_at && (
                <span className={styles.elapsed}>
                  {formatElapsed(run.started_at, run.finished_at, t)}
                </span>
              )}
            </>
          )}
        </div>
      }
      open={open}
      onClose={onClose}
      footer={
        <div className={styles.footer}>
          <Button
            icon={<ReloadOutlined />}
            loading={loading}
            onClick={onRefresh}
          >
            {t('system.user.userSyncPage.progressDrawer.refresh')}
          </Button>
        </div>
      }
    >
      {!run ? (
        loading ? <Skeleton active paragraph={{ rows: 5 }} /> : <Empty description={t('system.user.userSyncPage.progressDrawer.empty')} />
      ) : (
        <Steps
          className={styles.steps}
          direction="vertical"
          current={currentStepIndex}
          items={phases.map((phase) => {
            const entry = safeGetPhaseProgress(payload, phase);
            const displayStatus = getPhaseDisplayStatus(phase, entry, payload);
            const displayEntry = { ...entry, status: displayStatus };
            const config = getPhaseStatusConfig(displayStatus, t);
            const isError = displayStatus === 'error';
            const errorMessage = isError && payload.phase_error?.phase === phase
              ? formatPhaseErrorMessage(payload, t)
              : '';
            const counterLine = formatPhaseCounterLine(phase, payload, t);
            const phaseResult = phase === 'finalize'
              ? formatEmailNotificationResult(payload, t)
              : formatPhaseBusinessResult(phase, payload, t);
            const displayProgress = getPhaseDisplayProgress(phase, displayEntry, payload);
            const progressEntry = { ...displayEntry, ...displayProgress };
            const progressMeta = formatPhaseProgressMeta(progressEntry, phaseResult || counterLine, t);
            const expandPhase = shouldExpandPhase(progressEntry);
            const timestamp = displayStatus === 'process' ? '' : entry.completed_at
              || (isError && payload.phase_error?.phase === phase ? payload.phase_error.failed_at : '');
            const timeLabel = timestamp
              ? t(
                isError
                  ? 'system.user.userSyncPage.progressDrawer.phaseFailedAt'
                  : 'system.user.userSyncPage.progressDrawer.phaseCompletedAt',
              ).replace('{{time}}', convertToLocalizedTime(timestamp, 'YYYY-MM-DD HH:mm:ss'))
              : '';

            return {
              status: config.stepStatus,
              icon: phaseIcon[config.icon],
              title: (
                <div className={styles.phaseTitleRow}>
                  <span className={styles.phaseTitle}>{getPhaseLabel(phase, t)}</span>
                  <Tag bordered={false} color={config.tagColor} className={styles.phaseStatus}>
                    {config.text}
                  </Tag>
                </div>
              ),
              description: expandPhase ? (
                <div className={styles.phaseContent}>
                  {(phaseResult || progressMeta) && (
                    <div className={styles.phaseResult}>
                      {progressEntry.status === 'process' ? progressMeta : phaseResult}
                    </div>
                  )}
                  {progressEntry.status === 'process' && progressEntry.total > 0 && (
                    <Progress
                      percent={calcPercent(progressEntry.current, progressEntry.total)}
                      size="small"
                      showInfo={false}
                      className={styles.progress}
                    />
                  )}
                  {timeLabel && <div className={styles.phaseTimestamp}>{timeLabel}</div>}
                  {errorMessage && (
                    <Alert
                      className={styles.errorAlert}
                      type="error"
                      showIcon
                      message={t('system.user.userSyncPage.progressDrawer.failureReason')}
                      description={
                        <Typography.Text copyable={{ text: errorMessage }} className={styles.errorMessage}>
                          {errorMessage}
                        </Typography.Text>
                      }
                    />
                  )}
                </div>
              ) : null,
            };
          })}
        />
      )}
    </Drawer>
  );
};

export default UserSyncRunProgressDrawer;
