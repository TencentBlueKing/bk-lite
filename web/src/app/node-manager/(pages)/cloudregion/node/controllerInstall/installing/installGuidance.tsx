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
  deriveControllerInstallDisplay,
  deriveControllerInstallPhases,
  getControllerInstallDisplayLabel,
  getControllerInstallPhaseLabel,
  getInstallerFailureGuidance,
  getInstallerFailureSuggestion,
  getInstallerProgressPercent,
  getInstallerProgressText,
  getInstallerSummaryGuidance,
  getInstallerStepInfo,
  getInstallerStepLabel,
  normalizeInstallerLogs,
  normalizeInstallerSummary,
  shouldUseControllerInstallPhases
} from '@/app/node-manager/utils/installerProgress';
import { useTranslation } from '@/utils/i18n';
import { useLocalizedTime } from '@/hooks/useLocalizedTime';

interface InstallGuidanceProps {
  onClose?: () => void;
}

type InstallGuidanceDisplayMode = 'controllerInstall' | 'stepList';

const InstallGuidance = forwardRef<ModalRef, InstallGuidanceProps>(
  ({ onClose }, ref) => {
    const { t } = useTranslation();
    const { convertToLocalizedTime } = useLocalizedTime();
    const [groupVisible, setGroupVisible] = useState<boolean>(false);
    const [title, setTitle] = useState<string>('');
    const [logs, setLogs] = useState<LogStep[]>([]);
    const [installerSummary, setInstallerSummary] =
      useState<InstallerEventSummary | undefined>();
    const [displayMode, setDisplayMode] =
      useState<InstallGuidanceDisplayMode | undefined>();
    const [nodeInfo, setNodeInfo] = useState({ ip: '', nodeName: '' });

    useImperativeHandle(ref, () => ({
      showModal: ({ title, form }) => {
        setGroupVisible(true);
        setTitle(title || '');
        setLogs(normalizeInstallerLogs(form?.logs));
        setInstallerSummary(normalizeInstallerSummary(form?.installerSummary));
        setDisplayMode(form?.displayMode);
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
        setDisplayMode(undefined);
        onClose?.();
      }
    }));

    const handleCancel = () => {
      setGroupVisible(false);
      setInstallerSummary(undefined);
      setDisplayMode(undefined);
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

    const getPhaseStatusConfig = (status: string, displayLabel?: string): StatusConfig => {
      const phaseStatusConfigs: Record<string, StatusConfig> = {
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
        warning: {
          text: displayLabel || t('node-manager.cloudregion.node.installStateInstallerNoReport'),
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
        },
        waiting: {
          text: t('node-manager.cloudregion.node.installStateWaiting'),
          tagColor: 'processing',
          borderColor: 'var(--color-border-2)',
          stepStatus: 'finish',
          icon: <ClockCircleFilled style={{ color: 'var(--color-text-3)' }} />
        }
      };

      return phaseStatusConfigs[status] || phaseStatusConfigs.waiting;
    };

    const installerDetailSteps =
      installerSummary?.steps?.length
        ? installerSummary.steps
        : logs.filter((log) => log.details?.installer_event);
    const phaseResult = {
      steps: logs,
      installer_summary: installerSummary
    };
    const shouldRenderControllerPhases = shouldUseControllerInstallPhases(
      phaseResult,
      displayMode
    );
    const installDisplay = deriveControllerInstallDisplay(phaseResult);
    const installPhases = deriveControllerInstallPhases(phaseResult);
    const summaryGuidance = getInstallerSummaryGuidance(t, installerSummary);
    const shouldShowConnectivityGuidance =
      !!summaryGuidance &&
      ['installer_success_connectivity_pending', 'installer_success_connectivity_timeout'].includes(
        installerSummary?.state || ''
      );
    const logByAction = (action: string) =>
      [...logs].reverse().find((log) => log.action === action);
    const phaseLogActionMap = {
      credential_validation: 'credential_check',
      command_dispatch: 'run',
      node_connectivity: 'connectivity_check'
    } as const;

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
            {shouldRenderControllerPhases ? (
            <Steps
              direction="vertical"
              current={installPhases.filter((phase) => phase.status !== 'waiting').length}
              items={installPhases.map((phase) => {
                const mappedAction =
                  phase.code in phaseLogActionMap
                    ? phaseLogActionMap[phase.code as keyof typeof phaseLogActionMap]
                    : null;
                const log = mappedAction ? logByAction(mappedAction) : null;
                const phaseDisplayLabel =
                  phase.code === installDisplay.phase
                    ? getControllerInstallDisplayLabel(t, installDisplay)
                    : undefined;
                const statusConfig = getPhaseStatusConfig(
                  phase.status,
                  phaseDisplayLabel
                );
                const stepProgress = log?.details?.progress;
                const progressPercent = getInstallerProgressPercent(stepProgress);
                const progressText = getInstallerProgressText(stepProgress);
                const stepInfo = getInstallerStepInfo(
                  log?.details?.step_index,
                  log?.details?.step_total
                );
                const failureSuggestion = getInstallerFailureSuggestion(
                  t,
                  log?.details?.raw_step || log?.action
                );
                const failureGuidance = getInstallerFailureGuidance(t, {
                  steps: log ? [log] : []
                });
                const isFailureLog =
                  phase.status === 'error' ||
                  ['error', 'timeout'].includes(log?.status || '');
                const isInstallerPhase = phase.code === 'installer_execution';
                const isConnectivityStep = phase.code === 'node_connectivity';
                return {
                  status: statusConfig.stepStatus,
                  icon: statusConfig.icon,
                  title: (
                    <div className="flex items-center justify-between">
                      <span className="text-[14px] font-medium">
                        {getControllerInstallPhaseLabel(t, phase.code)}
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
                          {log?.timestamp
                            ? convertToLocalizedTime(log.timestamp)
                            : '--'}
                          ]
                        </div>
                          <div className="text-[12px] text-[var(--color-text-1)]">
                            {isInstallerPhase && phase.detailState === 'no_report'
                              ? t('node-manager.cloudregion.node.installerStepsNotReceived')
                              : log?.message || phaseDisplayLabel || '--'}
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
                              status={log?.status === 'error' ? 'exception' : 'active'}
                              showInfo={false}
                            />
                          </div>
                        )}
                        {isFailureLog && failureGuidance.reason && (
                          <div className="mt-[8px] text-[12px] text-[var(--color-error)]">
                            {t('node-manager.cloudregion.node.failureReason')}:
                            {' '}
                            {failureGuidance.reason}
                          </div>
                        )}
                        {isFailureLog && !!failureGuidance.context?.length && (
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
                        {(phase.status === 'error' || phase.status === 'warning') && (
                          <div className="mt-[4px] text-[12px] text-[var(--color-text-2)]">
                            {t('node-manager.cloudregion.node.nextAction')}:
                            {' '}
                            {summaryGuidance || failureGuidance.suggestion || failureSuggestion}
                          </div>
                        )}
                        {isInstallerPhase && phase.detailState !== 'none' && installerSummary && (
                          <div className="mt-[10px] border-t border-[var(--color-border-1)] pt-[10px]">
                            <div className="flex flex-wrap items-center gap-[8px] text-[12px] text-[var(--color-text-2)]">
                              <span>
                                {t('node-manager.cloudregion.node.installerDetailProgress')}:
                                {' '}
                                {phase.detailState === 'no_report'
                                  ? t('node-manager.cloudregion.node.installerStepsNotReceived')
                                  : `${installerSummary?.completed_count ?? 0}/${installerSummary?.expected_count ?? installerDetailSteps.length}`}
                              </span>
                            </div>
                            {phase.showMissingSteps && !!installerSummary?.missing_steps?.length && (
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
            ) : (
              <Steps
                direction="vertical"
                current={logs.filter((log) => log.status !== 'waiting').length}
                items={(logs.length ? logs : [{
                  action: 'waiting',
                  status: 'waiting',
                  message: '--',
                  timestamp: ''
                }]).map((log, index) => {
                  const statusConfig = getStatusConfig(log.status);
                  const stepProgress = log.details?.progress;
                  const progressPercent = getInstallerProgressPercent(stepProgress);
                  const progressText = getInstallerProgressText(stepProgress);
                  const stepInfo = getInstallerStepInfo(
                    log.details?.step_index,
                    log.details?.step_total
                  );
                  const failureGuidance = getInstallerFailureGuidance(t, {
                    steps: [log]
                  });
                  const isFailureLog = ['error', 'timeout'].includes(log.status);
                  return {
                    status: statusConfig.stepStatus,
                    icon: statusConfig.icon,
                    title: (
                      <div className="flex items-center justify-between">
                        <span className="text-[14px] font-medium">
                          {getInstallerStepLabel(
                            t,
                            log.details?.raw_step || log.action,
                            log.action
                          )}
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
                          <div className="break-words text-[12px] text-[var(--color-text-1)]">
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
                                status={isFailureLog ? 'exception' : 'active'}
                                showInfo={false}
                              />
                            </div>
                          )}
                          {isFailureLog && failureGuidance.reason && (
                            <div className="mt-[8px] text-[12px] text-[var(--color-error)]">
                              {t('node-manager.cloudregion.node.failureReason')}:
                              {' '}
                              {failureGuidance.reason}
                            </div>
                          )}
                          {isFailureLog && !!failureGuidance.context?.length && (
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
                          {isFailureLog && (
                            <div className="mt-[4px] text-[12px] text-[var(--color-text-2)]">
                              {t('node-manager.cloudregion.node.nextAction')}:
                              {' '}
                              {failureGuidance.suggestion}
                            </div>
                          )}
                        </div>
                      </div>
                    ),
                    key: `${log.action}-${index}`
                  };
                })}
              />
            )}
          </div>
        </OperateDrawer>
      </div>
    );
  }
);
InstallGuidance.displayName = 'InstallGuidance';
export default InstallGuidance;
