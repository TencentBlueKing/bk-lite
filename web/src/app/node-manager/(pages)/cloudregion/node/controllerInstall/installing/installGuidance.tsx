'use client';

import React, { useState, forwardRef, useImperativeHandle } from 'react';
import { Progress, Steps, Tag } from 'antd';
import {
  CheckCircleFilled,
  CloseCircleFilled,
  LoadingOutlined,
  ClockCircleFilled
} from '@ant-design/icons';
import OperateDrawer from '@/app/node-manager/components/operate-drawer';
import { ModalRef } from '@/app/node-manager/types';
import {
  InstallerEventSummary,
  LogStep,
  StatusConfig
} from '@/app/node-manager/types/controller';
import {
  getInstallerFailureGuidance,
  getInstallerFailureSuggestion,
  getInstallerProgressPercent,
  getInstallerProgressText,
  getInstallerSummaryGuidance,
  getInstallerStepInfo,
  getInstallerStepLabel,
  normalizeInstallerLogs,
  normalizeInstallerSummary
} from '@/app/node-manager/utils/installerProgress';
import { useTranslation } from '@/utils/i18n';
import { useLocalizedTime } from '@/hooks/useLocalizedTime';

interface InstallGuidanceProps {
  onClose?: () => void;
}

const InstallGuidance = forwardRef<ModalRef, InstallGuidanceProps>(
  ({ onClose }, ref) => {
    const { t } = useTranslation();
    const { convertToLocalizedTime } = useLocalizedTime();
    const [groupVisible, setGroupVisible] = useState<boolean>(false);
    const [title, setTitle] = useState<string>('');
    const [logs, setLogs] = useState<LogStep[]>([]);
    const [installerSummary, setInstallerSummary] =
      useState<InstallerEventSummary | undefined>();
    const [nodeInfo, setNodeInfo] = useState({ ip: '', nodeName: '' });

    useImperativeHandle(ref, () => ({
      showModal: ({ title, form }) => {
        setGroupVisible(true);
        setTitle(title || '');
        setLogs(normalizeInstallerLogs(form?.logs));
        setInstallerSummary(normalizeInstallerSummary(form?.installerSummary));
        setNodeInfo({
          ip: form?.ip || '',
          nodeName: form?.nodeName || ''
        });
      },
      updateLogs: (
        newLogs: LogStep[],
        newNodeInfo?: { ip?: string; nodeName?: string },
        newInstallerSummary?: InstallerEventSummary
      ) => {
        setLogs(normalizeInstallerLogs(newLogs));
        setInstallerSummary(normalizeInstallerSummary(newInstallerSummary));
        // 如果提供了新的节点信息，也更新它
        if (newNodeInfo) {
          setNodeInfo((prev) => ({
            ip: newNodeInfo.ip || prev.ip,
            nodeName: newNodeInfo.nodeName || prev.nodeName
          }));
        }
      },
      closeModal: () => {
        setGroupVisible(false);
        setInstallerSummary(undefined);
        onClose?.();
      }
    }));

    const handleCancel = () => {
      setGroupVisible(false);
      setInstallerSummary(undefined);
      onClose?.();
    };

    // 统一的状态配置方法
    const getStatusConfig = (status: string): StatusConfig => {
      const statusConfigs: Record<string, StatusConfig> = {
        success: {
          text: t('node-manager.cloudregion.node.statusCompleted'),
          tagColor: 'success',
          borderColor: '#52c41a',
          stepStatus: 'finish',
          icon: <CheckCircleFilled style={{ color: '#52c41a' }} />
        },
        error: {
          text: t('node-manager.cloudregion.node.failed'),
          tagColor: 'error',
          borderColor: '#ff4d4f',
          stepStatus: 'finish',
          icon: <CloseCircleFilled style={{ color: '#ff4d4f' }} />
        },
        timeout: {
          text: t('node-manager.cloudregion.node.timeout'),
          tagColor: 'warning',
          borderColor: '#faad14',
          stepStatus: 'finish',
          icon: <ClockCircleFilled style={{ color: '#faad14' }} />
        },
        running: {
          text: t('node-manager.cloudregion.node.statusRunning'),
          tagColor: 'processing',
          borderColor: 'var(--color-primary)',
          stepStatus: 'finish',
          icon: <LoadingOutlined />
        }
      };

      return (
        statusConfigs[status] || {
          text: status,
          tagColor: 'processing' as const,
          borderColor: 'var(--color-primary)',
          stepStatus: 'finish' as const,
          icon: <LoadingOutlined />
        }
      );
    };

    const installerDetailSteps =
      installerSummary?.steps?.length
        ? installerSummary.steps
        : logs.filter((log) => log.details?.installer_event);
    const visibleLogs = logs.filter((log) => !log.details?.installer_event);
    const displayLogs = visibleLogs.length ? visibleLogs : logs;
    const summaryGuidance = getInstallerSummaryGuidance(t, installerSummary);
    const shouldShowSummaryOnRun =
      !!installerSummary &&
      (installerDetailSteps.length > 0 ||
        ['no_installer_events', 'incomplete_installer_events'].includes(
          installerSummary.state || ''
        ));
    const shouldShowConnectivityGuidance =
      !!summaryGuidance &&
      ['installer_success_connectivity_pending', 'installer_success_connectivity_timeout'].includes(
        installerSummary?.state || ''
      );

    return (
      <div>
        <OperateDrawer
          width={700}
          title={title}
          visible={groupVisible}
          onClose={handleCancel}
          headerExtra={
            <div className="flex items-center gap-2">
              <span className="text-[12px] text-[var(--color-text-3)]">
                {t('node-manager.cloudregion.node.ipaddress')}：
              </span>
              <span className="text-[12px]">{nodeInfo.ip || '--'}</span>
              <span className="text-[12px] text-[var(--color-text-3)] ml-[16px]">
                {t('node-manager.cloudregion.node.nodeName')}：
              </span>
              <span className="text-[12px]">{nodeInfo.nodeName || '--'}</span>
            </div>
          }
        >
          <div className="p-[16px]">
            {/* 安装步骤 */}
            <Steps
              direction="vertical"
              current={displayLogs.length}
              items={displayLogs.map((log) => {
                const statusConfig = getStatusConfig(log.status);
                const stepProgress = log.details?.progress;
                const progressPercent = getInstallerProgressPercent(stepProgress);
                const progressText = getInstallerProgressText(stepProgress);
                const stepInfo = getInstallerStepInfo(
                  log.details?.step_index,
                  log.details?.step_total
                );
                const displayAction = getInstallerStepLabel(
                  t,
                  log.details?.raw_step || log.action,
                  log.action
                );
                const failureSuggestion = getInstallerFailureSuggestion(
                  t,
                  log.details?.raw_step || log.action
                );
                const failureGuidance = getInstallerFailureGuidance(t, {
                  steps: [log]
                });
                const isRunInstallerStep = log.action === 'run';
                const isConnectivityStep = log.action === 'connectivity_check';
                return {
                  status: statusConfig.stepStatus,
                  icon: statusConfig.icon,
                  title: (
                    <div className="flex items-center justify-between">
                      <span className="text-[14px] font-medium">
                        {displayAction}
                      </span>
                      <Tag
                        className="ml-[10px]"
                        color={statusConfig.tagColor}
                        bordered={false}
                      >
                        {statusConfig.text}
                      </Tag>
                    </div>
                  ),
                  description: (
                    <div className="mt-[8px]">
                      <div
                        className="p-[12px] bg-[var(--color-fill-1)] rounded-[4px]"
                        style={{
                          borderLeft: `4px solid ${statusConfig.borderColor}`,
                          border: `1px solid var(--color-border-1)`,
                          borderLeftWidth: '4px',
                          borderLeftColor: statusConfig.borderColor
                        }}
                      >
                        <div className="text-[12px] text-[var(--color-text-3)] mb-[4px]">
                          [
                          {log.timestamp
                            ? convertToLocalizedTime(log.timestamp)
                            : '--'}
                          ]
                        </div>
                          <div className="text-[12px] text-[var(--color-text-1)]">
                            {log.message || '--'}
                          </div>
                        {(stepInfo || progressText) && (
                          <div className="mt-[8px] flex flex-wrap items-center gap-[8px] text-[12px] text-[var(--color-text-2)]">
                            {stepInfo && (
                              <Tag bordered={false} color="default" className="m-0">
                                {stepInfo}
                              </Tag>
                            )}
                            {progressText && <span>{progressText}</span>}
                          </div>
                        )}
                        {progressPercent !== null && (
                          <div className="mt-[8px]">
                            <Progress
                              percent={progressPercent}
                              size="small"
                              status={log.status === 'error' ? 'exception' : 'active'}
                              showInfo={false}
                            />
                          </div>
                        )}
                        {failureGuidance.reason && (
                          <div className="mt-[8px] text-[12px] text-[var(--color-error)]">
                            {t('node-manager.cloudregion.node.failureReason')}:
                            {' '}
                            {failureGuidance.reason}
                          </div>
                        )}
                        {!!failureGuidance.context?.length && (
                          <div className="mt-[4px] text-[12px] text-[var(--color-text-3)]">
                            <div className="mb-[2px]">
                              {t('node-manager.cloudregion.node.failureContext')}:
                            </div>
                            <div className="space-y-[2px]">
                              {failureGuidance.context.map((entry) => (
                                <div key={entry}>{entry}</div>
                              ))}
                            </div>
                          </div>
                        )}
                        {['error', 'timeout'].includes(log.status) && (
                          <div className="mt-[4px] text-[12px] text-[var(--color-text-2)]">
                            {t('node-manager.cloudregion.node.nextAction')}:
                            {' '}
                            {failureGuidance.suggestion || failureSuggestion}
                          </div>
                        )}
                        {isRunInstallerStep && shouldShowSummaryOnRun && (
                          <div className="mt-[10px] border-t border-[var(--color-border-1)] pt-[10px]">
                            <div className="flex flex-wrap items-center gap-[8px] text-[12px] text-[var(--color-text-2)]">
                              <span>
                                {t('node-manager.cloudregion.node.installerDetailProgress')}:
                                {' '}
                                {installerSummary?.completed_count ?? 0}
                                /
                                {installerSummary?.expected_count ?? installerDetailSteps.length}
                              </span>
                              {!!installerSummary?.duplicate_count && (
                                <Tag bordered={false} color="warning" className="m-0">
                                  {t('node-manager.cloudregion.node.installerDetailDuplicated')}:
                                  {' '}
                                  {installerSummary.duplicate_count}
                                </Tag>
                              )}
                            </div>
                            {!!installerSummary?.missing_steps?.length && (
                              <div className="mt-[6px] text-[12px] text-[var(--color-warning)]">
                                {t('node-manager.cloudregion.node.installerDetailMissing')}:
                                {' '}
                                {installerSummary.missing_steps
                                  .map((step) => getInstallerStepLabel(t, step, step))
                                  .join(', ')}
                              </div>
                            )}
                            {summaryGuidance && (
                              <div className="mt-[6px] text-[12px] text-[var(--color-text-2)]">
                                {t('node-manager.cloudregion.node.nextAction')}:
                                {' '}
                                {summaryGuidance}
                              </div>
                            )}
                            {!!installerDetailSteps.length && (
                              <div className="mt-[8px] space-y-[6px]">
                                {installerDetailSteps.map((step, index) => {
                                  const detailStatusConfig = getStatusConfig(step.status);
                                  return (
                                    <div
                                      key={`${step.action}-${index}`}
                                      className="flex items-start justify-between gap-[8px] rounded-[4px] bg-[var(--color-fill-2)] px-[10px] py-[8px]"
                                    >
                                      <div className="min-w-0">
                                        <div className="text-[12px] font-medium text-[var(--color-text-1)]">
                                          {getInstallerStepLabel(
                                            t,
                                            step.details?.raw_step || step.action,
                                            step.action
                                          )}
                                        </div>
                                        <div className="mt-[2px] break-words text-[12px] text-[var(--color-text-3)]">
                                          {step.message || '--'}
                                        </div>
                                      </div>
                                      <Tag
                                        className="m-0 shrink-0"
                                        color={detailStatusConfig.tagColor}
                                        bordered={false}
                                      >
                                        {detailStatusConfig.text}
                                      </Tag>
                                    </div>
                                  );
                                })}
                              </div>
                            )}
                          </div>
                        )}
                        {isConnectivityStep && shouldShowConnectivityGuidance && (
                          <div className="mt-[8px] text-[12px] text-[var(--color-text-2)]">
                            {t('node-manager.cloudregion.node.nextAction')}:
                            {' '}
                            {summaryGuidance}
                          </div>
                        )}
                      </div>
                    </div>
                  )
                };
              })}
            />
          </div>
        </OperateDrawer>
      </div>
    );
  }
);
InstallGuidance.displayName = 'InstallGuidance';
export default InstallGuidance;
