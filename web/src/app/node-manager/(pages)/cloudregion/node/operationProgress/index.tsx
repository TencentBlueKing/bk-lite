'use client';
import React, { useEffect, useState, useRef, useMemo } from 'react';
import { Button, Tag, notification, Modal, Alert, Progress, Tooltip } from 'antd';
import type { TableColumnsType } from 'antd';
import {
  CheckCircleOutlined,
  CheckCircleFilled,
  CloseCircleOutlined,
  ClockCircleOutlined,
  SyncOutlined,
  ExclamationCircleFilled
} from '@ant-design/icons';
import useApiClient from '@/utils/request';
import { useTranslation } from '@/utils/i18n';
import { ModalRef, TableDataItem } from '@/app/node-manager/types';
import { OPERATE_SYSTEMS } from '@/app/node-manager/constants/cloudregion';
import { useGroupNames } from '@/app/node-manager/hooks/node';
import { useHandleCopy } from '@/app/node-manager/hooks';
import CustomTable from '@/components/custom-table';
import useNodeManagerApi from '@/app/node-manager/api';
import useControllerApi from '@/app/node-manager/api/useControllerApi';
import InstallGuidance from '@/app/node-manager/(pages)/cloudregion/node/controllerInstall/installing/installGuidance';
import RetryInstallModal from '@/app/node-manager/(pages)/cloudregion/node/controllerInstall/installing/retryInstallModal';
import OperationGuidance from '@/app/node-manager/(pages)/cloudregion/node/controllerInstall/installing/operationGuidance';
import Icon from '@/components/icon';
import {
  ControllerInstallProgressRow,
  ControllerManualInstallStatusItem
} from '@/app/node-manager/types/controller';
import {
  deriveControllerInstallDisplay,
  getControllerInstallDisplayLabel,
  getInstallerFailureGuidance,
  getInstallerProgressPercent,
  getInstallerProgressText,
  getInstallerSummaryProgressInfo,
  getInstallerSummaryGuidance,
  getInstallerStepInfo,
  getInstallerSummaryLabel,
  normalizeControllerInstallResult,
  normalizeControllerInstallRows,
  normalizeInstallerStatus
} from '@/app/node-manager/utils/installerProgress';

// 操作类型
export type OperationType =
  | 'installController'
  | 'uninstallController'
  | 'installCollector'
  | 'startCollector'
  | 'restartCollector'
  | 'stopCollector';

// 文案配置
export interface OperationTextConfig {
  listTitle: string; // 列表标题
  statusColumn: string; // 状态列标题
  finishButton: string; // 结束按钮文案
}

export interface OperationProgressProps {
  operationType: OperationType;
  taskIds: string;
  installMethod?: 'remoteInstall' | 'manualInstall';
  manualTaskList?: TableDataItem[];
  textConfig?: Partial<OperationTextConfig>;
  collectorId?: string; // 组件ID，用于启动/停止/重启重试
  collectorPackageId?: number; // 组件安装包ID，用于安装重试
  onNext: () => void;
  cancel: () => void;
}

const renderInstallerProgressSummary = (
  summaryLabel: string | null,
  stepInfo: string | null,
  progressText: string | null,
  progressPercent: number | null
) => {
  if (!summaryLabel && !stepInfo && !progressText && progressPercent === null) {
    return null;
  }

  return (
    <div className="mt-[8px] min-w-0 max-w-[240px]">
      {summaryLabel && (
        <div className="truncate text-[12px] text-[var(--color-text-2)]">
          {summaryLabel}
        </div>
      )}
      {(stepInfo || progressText) && (
        <div className="mt-[2px] flex flex-wrap items-center gap-[8px] text-[12px] text-[var(--color-text-3)]">
          {stepInfo && <span>{stepInfo}</span>}
          {progressText && <span>{progressText}</span>}
        </div>
      )}
      {progressPercent !== null && (
        <div className="mt-[6px]">
          <Progress percent={progressPercent} size="small" showInfo={false} />
        </div>
      )}
    </div>
  );
};

const DEFAULT_POLL_INTERVAL = 5000;
const CONTROLLER_INSTALL_ACTIVE_POLL_INTERVAL = 2000;
const CONTROLLER_INSTALL_CONNECTIVITY_POLL_INTERVAL = 3000;
const AUTO_ADVANCE_DELAY = 5000;

const displaySeverityConfig = {
  success: { color: 'success', icon: <CheckCircleOutlined /> },
  error: { color: 'error', icon: <CloseCircleOutlined /> },
  warning: { color: 'warning', icon: <ClockCircleOutlined /> },
  processing: { color: 'processing', icon: <SyncOutlined spin /> },
  default: { color: 'default', icon: <ClockCircleOutlined /> }
};

const OperationProgress: React.FC<OperationProgressProps> = ({
  operationType,
  taskIds,
  installMethod = 'remoteInstall',
  manualTaskList = [],
  textConfig,
  collectorId,
  collectorPackageId,
  onNext,
  cancel
}) => {
  const { t } = useTranslation();
  const { isLoading } = useApiClient();
  const { handleCopy } = useHandleCopy();
  const {
    getControllerNodes,
    getCollectorNodes,
    getCollectorOperationNodes,
    installCollector,
    batchOperationCollector
  } = useNodeManagerApi();
  const { getManualInstallStatus, getInstallCommand } = useControllerApi();
  const { showGroupNames } = useGroupNames();
  const guidance = useRef<ModalRef>(null);
  const retryModalRef = useRef<ModalRef>(null);
  const operationGuidanceRef = useRef<ModalRef>(null);
  const timerRef = useRef<NodeJS.Timeout | null>(null);
  const [pageLoading, setPageLoading] = useState<boolean>(false);
  const [tableData, setTableData] = useState<ControllerInstallProgressRow[]>([]);
  // 使用 ref 保存 currentViewingNode 的最新值，避免闭包问题
  const currentViewingNodeRef = useRef<ControllerInstallProgressRow | null>(null);
  const [copyingNodeIds, setCopyingNodeIds] = useState<Array<string | number>>([]);
  const [retryingNodeIds, setRetryingNodeIds] = useState<string[]>([]);

  // 是否是安装控制器操作
  const isInstallController = operationType === 'installController';
  // 是否是卸载控制器操作
  const isUninstallController = operationType === 'uninstallController';
  // 是否是控制器相关操作（安装或卸载）
  const isControllerOperation = isInstallController || isUninstallController;

  const controllerInstallSummary = useMemo(() => {
    if (!isInstallController || tableData.length === 0) {
      return null;
    }

    const summary = tableData.reduce(
      (acc, item) => {
        if (['success', 'installed'].includes(item.status || '')) {
          acc.success += 1;
        } else if (item.status === 'error') {
          acc.error += 1;
        } else if (item.status === 'timeout') {
          acc.timeout += 1;
        } else {
          acc.running += 1;
        }

        return acc;
      },
      {
        total: tableData.length,
        success: 0,
        error: 0,
        timeout: 0,
        running: 0
      }
    );

    const completed = summary.success + summary.error + summary.timeout;

    return {
      ...summary,
      completed,
      percent:
        summary.total > 0
          ? Math.round((completed / summary.total) * 100)
          : 0
    };
  }, [isInstallController, tableData]);

  // 获取默认文案配置
  const defaultTextConfig: OperationTextConfig = useMemo(() => {
    // 状态列统一使用"状态"
    const statusColumn = t('node-manager.cloudregion.node.status');
    if (isInstallController) {
      return {
        listTitle: t('node-manager.controller.installList'),
        statusColumn,
        finishButton: t('node-manager.controller.finishInstall')
      };
    }
    if (isUninstallController) {
      return {
        listTitle: t('node-manager.controller.uninstallList'),
        statusColumn,
        finishButton: t('node-manager.controller.finishUninstall')
      };
    }
    return {
      listTitle: t('node-manager.controller.operationList'),
      statusColumn,
      finishButton: t('node-manager.controller.finishOperation')
    };
  }, [isInstallController, isUninstallController, t]);

  // 合并文案配置
  const mergedTextConfig: OperationTextConfig = {
    ...defaultTextConfig,
    ...textConfig
  };

  // 根据操作类型获取状态文案
  const getStatusTextByOperation = useMemo(() => {
    const textMap: Record<
      OperationType,
      {
        success: string;
        error: string;
        timeout: string;
        running: string;
      }
    > = {
      installController: {
        success: t('node-manager.cloudregion.node.installSuccess'),
        error: t('node-manager.cloudregion.node.installError'),
        timeout: t('node-manager.cloudregion.node.installTimeout'),
        running: t('node-manager.cloudregion.node.remoteInstalling')
      },
      uninstallController: {
        success: t('node-manager.cloudregion.node.successUninstall'),
        error: t('node-manager.cloudregion.node.failUninstall'),
        timeout: t('node-manager.cloudregion.node.uninstallTimeout'),
        running: t('node-manager.cloudregion.node.uninstalling')
      },
      installCollector: {
        success: t('node-manager.cloudregion.node.installSuccess'),
        error: t('node-manager.cloudregion.node.installError'),
        timeout: t('node-manager.cloudregion.node.installTimeout'),
        running: t('node-manager.cloudregion.node.remoteInstalling')
      },
      startCollector: {
        success: t('node-manager.cloudregion.node.startSuccess'),
        error: t('node-manager.cloudregion.node.startError'),
        timeout: t('node-manager.cloudregion.node.startTimeout'),
        running: t('node-manager.cloudregion.node.starting')
      },
      stopCollector: {
        success: t('node-manager.cloudregion.node.stopSuccess'),
        error: t('node-manager.cloudregion.node.stopError'),
        timeout: t('node-manager.cloudregion.node.stopTimeout'),
        running: t('node-manager.cloudregion.node.stopping')
      },
      restartCollector: {
        success: t('node-manager.cloudregion.node.restartSuccess'),
        error: t('node-manager.cloudregion.node.restartError'),
        timeout: t('node-manager.cloudregion.node.restartTimeout'),
        running: t('node-manager.cloudregion.node.restarting')
      }
    };
    return textMap[operationType];
  }, [operationType, t]);

  // 状态映射
  const statusMap = useMemo(() => {
    const isManualInstall = installMethod === 'manualInstall';
    const statusTexts = getStatusTextByOperation;
    return {
      success: {
        color: 'success',
        text: statusTexts.success,
        icon: <CheckCircleOutlined />
      },
      installed: {
        color: 'success',
        text: statusTexts.success,
        icon: <CheckCircleOutlined />
      },
      error: {
        color: 'error',
        text: statusTexts.error,
        icon: <CloseCircleOutlined />
      },
      timeout: {
        color: 'error',
        text: statusTexts.timeout,
        icon: <ClockCircleOutlined />
      },
      waiting: {
        color: 'processing',
        text: isManualInstall
          ? t('node-manager.cloudregion.node.waitingManual')
          : statusTexts.running,
        icon: <SyncOutlined spin />
      },
      installing: {
        color: 'processing',
        text: statusTexts.running,
        icon: <SyncOutlined spin />
      },
      running: {
        color: 'processing',
        text: statusTexts.running,
        icon: <SyncOutlined spin />
      }
    };
  }, [t, installMethod, getStatusTextByOperation]);

  const columns = useMemo<TableColumnsType<ControllerInstallProgressRow>>(() => {
    const baseColumns: TableColumnsType<ControllerInstallProgressRow> = [
      {
        title: t('node-manager.cloudregion.node.ipAdrress'),
        dataIndex: 'ip',
        width: 100,
        key: 'ip'
      },
      {
        title: t('node-manager.cloudregion.node.nodeName'),
        dataIndex: 'node_name',
        width: 120,
        key: 'node_name',
        ellipsis: true,
        render: (value: string) => value || '--'
      },
      {
        title: t('node-manager.cloudregion.node.operateSystem'),
        dataIndex: 'os',
        width: 120,
        key: 'os',
        ellipsis: true,
        render: (value: string) => {
          const osLabel =
            OPERATE_SYSTEMS.find((item) => item.value === value)?.label || '--';
          const iconType = value === 'linux' ? 'Linux' : 'Window-Windows';
          return (
            <Tag
              color="blue"
              bordered={false}
              className="flex items-center gap-1 w-fit"
            >
              <Icon type={iconType} className="text-[16px]" />
              <span>{osLabel}</span>
            </Tag>
          );
        }
      },
      {
        title: t('node-manager.cloudregion.node.organization'),
        dataIndex: 'organizations',
        width: 100,
        key: 'organizations',
        ellipsis: true,
        render: (value: string[]) => {
          return <>{showGroupNames(value || []) || '--'}</>;
        }
      }
    ];

    // 所有操作类型都显示安装方式列
    // baseColumns.push({
    //   title: t('node-manager.cloudregion.node.installationMethod'),
    //   dataIndex: 'install_method',
    //   width: 100,
    //   key: 'install_method',
    //   ellipsis: true,
    //   render: () => {
    //     const installWay =
    //       installMethod === 'manualInstall'
    //         ? t('node-manager.cloudregion.node.manualInstall')
    //         : t('node-manager.cloudregion.node.remoteInstall');
    //     return <>{installWay}</>;
    //   }
    // });

    // 状态列
    baseColumns.push({
      title: mergedTextConfig.statusColumn,
      dataIndex: 'status',
      width: 240,
      key: 'status',
      ellipsis: true,
      render: (value: string, row: ControllerInstallProgressRow) => {
        const normalizedStatus = normalizeInstallerStatus(value);
        const normalizedResult = normalizeControllerInstallResult(row.result);
        const controllerDisplay =
          isInstallController && installMethod === 'remoteInstall'
            ? deriveControllerInstallDisplay(normalizedResult)
            : null;
        const displayConfig = controllerDisplay
          ? displaySeverityConfig[
            controllerDisplay.severity as keyof typeof displaySeverityConfig
          ] || displaySeverityConfig.default
          : null;
        const status = controllerDisplay
          ? {
            color: displayConfig?.color || 'processing',
            text: getControllerInstallDisplayLabel(t, controllerDisplay),
            icon: displayConfig?.icon || <SyncOutlined spin />
          }
          : statusMap[normalizedStatus as keyof typeof statusMap];
        if (!status) {
          return <span>--</span>;
        }

        const installerProgress =
          isInstallController && installMethod === 'remoteInstall'
            ? normalizedResult?.installer_progress
            : undefined;
        const summaryLabel =
          controllerDisplay?.state === 'installer_no_report'
            ? t('node-manager.cloudregion.node.installerStepsNotReceived')
            : getInstallerSummaryLabel(t, installerProgress);
        const summaryProgressInfo = getInstallerSummaryProgressInfo(
          normalizedResult?.installer_summary
        );
        const stepInfo = summaryProgressInfo?.stepInfo || getInstallerStepInfo(
          installerProgress?.step_index,
          installerProgress?.step_total
        );
        const progressText = getInstallerProgressText(
          installerProgress?.progress
        );
        const progressPercent = summaryProgressInfo?.percent ?? getInstallerProgressPercent(
          installerProgress?.progress
        );
        const failureGuidance = getInstallerFailureGuidance(t, row.result);
        const summaryGuidance = getInstallerSummaryGuidance(
          t,
          normalizedResult?.installer_summary
        );

        const hasFailureInfo =
          ['error', 'timeout'].includes(normalizedStatus) ||
          ['error', 'warning'].includes(controllerDisplay?.severity || '');
        const hasTooltipContent =
          hasFailureInfo &&
          (failureGuidance.reason || failureGuidance.suggestion || summaryGuidance);

        const tooltipContent = hasTooltipContent ? (
          <div className="max-w-[320px] text-[12px]">
            {failureGuidance.reason && (
              <div>
                {t('node-manager.cloudregion.node.failureReason')}:
                {' '}
                {failureGuidance.reason}
              </div>
            )}
            {!!failureGuidance.context?.length && (
              <div className="mt-[4px]">
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
            {failureGuidance.suggestion && (
              <div className="mt-[4px]">
                {t('node-manager.cloudregion.node.nextAction')}:
                {' '}
                {failureGuidance.suggestion}
              </div>
            )}
            {summaryGuidance && (
              <div className="mt-[4px]">
                {t('node-manager.cloudregion.node.nextAction')}:
                {' '}
                {summaryGuidance}
              </div>
            )}
          </div>
        ) : null;

        return (
          <div>
            <Tooltip title={tooltipContent} overlayStyle={{ maxWidth: 360 }}>
              <Tag
                color={status.color}
                bordered={false}
                icon={status.icon}
                className="flex items-center gap-1 w-fit cursor-pointer"
              >
                <span>{status.text}</span>
              </Tag>
            </Tooltip>
            {renderInstallerProgressSummary(
              summaryLabel,
              stepInfo,
              progressText,
              progressPercent
            )}
          </div>
        );
      }
    });

    // 操作列
    baseColumns.push({
      title: t('common.actions'),
      dataIndex: 'action',
      width: 200,
      fixed: 'right',
      key: 'action',
      render: (value: string, row: ControllerInstallProgressRow) => {
        const isManualInstall = installMethod === 'manualInstall';
        const isWindows = row.os === 'windows';
        const nodeId = row.node_id || row.id;
        // 卸载控制器不显示重试按钮
        const showRetry =
          ['error', 'timeout'].includes(row.status) && !isUninstallController;

        // 只有安装控制器才显示手动安装相关操作
        if (isInstallController && isManualInstall) {
          return (
            <>
              {isWindows && (
                <Button
                  type="link"
                  className="mr-[10px]"
                  onClick={() => handleOperationGuidance(row)}
                >
                  {t('node-manager.cloudregion.node.operationGuidance')}
                </Button>
              )}
              <Button
                type="link"
                loading={copyingNodeIds.includes(row.id as any)}
                onClick={() => handleCopyInstallCommand(row)}
              >
                {t('node-manager.cloudregion.node.copyInstallCommand')}
              </Button>
            </>
          );
        }

        return (
          <>
            <Button
              type="link"
              onClick={() => checkDetail('remoteInstall', row)}
            >
              {t('node-manager.cloudregion.node.viewLog')}
            </Button>
            {showRetry && (
              <Button
                type="link"
                className="ml-[10px]"
                loading={retryingNodeIds.includes(String(nodeId))}
                onClick={() =>
                  isInstallController
                    ? handleRetry(row)
                    : handleCollectorRetry(row)
                }
              >
                {t('node-manager.cloudregion.node.retry')}
              </Button>
            )}
          </>
        );
      }
    });

    return baseColumns;
  }, [
    installMethod,
    copyingNodeIds,
    retryingNodeIds,
    isInstallController,
    isUninstallController,
    operationType,
    collectorId,
    collectorPackageId,
    mergedTextConfig.statusColumn,
    statusMap
  ]);

  useEffect(() => {
    if (taskIds && !isLoading) {
      getNodeList('refresh');
      schedulePolling();
      return () => {
        clearTimer();
      };
    }
  }, [taskIds, isLoading, isInstallController, installMethod]);

  const clearTimer = () => {
    if (timerRef.current) clearInterval(timerRef.current);
    timerRef.current = null;
  };

  const getPollingInterval = (rows?: ControllerInstallProgressRow[]) => {
    if (!isInstallController || installMethod !== 'remoteInstall') {
      return DEFAULT_POLL_INTERVAL;
    }

    const currentRows = rows ?? tableData;
    const runningRows = currentRows.filter((item) => item.status === 'running');

    if (runningRows.length === 0) {
      return DEFAULT_POLL_INTERVAL;
    }

    const hasActiveInstallerStep = runningRows.some((item) => {
      const normalizedResult = normalizeControllerInstallResult(item.result);
      const installerProgress = normalizedResult?.installer_progress;

      if (installerProgress?.current_status === 'running') {
        return true;
      }

      const steps = normalizedResult?.steps || [];
      const runningStep = [...steps].reverse().find((step) => step.status === 'running');
      return !!runningStep && runningStep.action !== 'connectivity_check';
    });

    return hasActiveInstallerStep
      ? CONTROLLER_INSTALL_ACTIVE_POLL_INTERVAL
      : CONTROLLER_INSTALL_CONNECTIVITY_POLL_INTERVAL;
  };

  const schedulePolling = (rows?: ControllerInstallProgressRow[]) => {
    clearTimer();
    timerRef.current = setInterval(() => {
      getNodeList('timer');
    }, getPollingInterval(rows));
  };

  // 重新启动轮询（重试成功后调用）
  const restartPolling = () => {
    getNodeList('refresh');
    schedulePolling();
  };

  const checkDetail = (type: string, row: ControllerInstallProgressRow) => {
    const logs = normalizeControllerInstallResult(row.result)?.steps || [];
    currentViewingNodeRef.current = row;
    guidance.current?.showModal({
      title: t('node-manager.cloudregion.node.viewLog'),
      type,
      form: {
        logs,
        installerSummary:
          normalizeControllerInstallResult(row.result)?.installer_summary,
        ip: row.ip,
        nodeName: row.node_name
      }
    });
  };

  const getNodeList = async (refreshType: string) => {
    try {
      setPageLoading(refreshType !== 'timer');
      let data: ControllerInstallProgressRow[] = [];
      let taskStatus: string = 'running';
      let taskSummary: {
        total: number;
        waiting: number;
        running: number;
        success: number;
        error: number;
      } | null = null;

      if (isControllerOperation) {
        // 控制器操作的逻辑（安装或卸载）
        if (installMethod === 'remoteInstall' || isUninstallController) {
          // 远程安装或卸载控制器，都使用 getControllerNodes 接口
          data = await getControllerNodes({ taskId: taskIds });
        } else {
          // 手动安装控制器
          if (manualTaskList.length > 0) {
            const statusData = await getManualInstallStatus({
              node_ids: taskIds
            });
            data = manualTaskList.map((item: TableDataItem) => {
              const statusInfo = statusData.find(
                (status: ControllerManualInstallStatusItem) =>
                  status.node_id === item.node_id
              );
              return {
                ...item,
                status: normalizeInstallerStatus(statusInfo?.status),
                result: normalizeControllerInstallResult(statusInfo?.result)
              };
            });
          }
        }
      } else {
        // 组件操作的逻辑
        if (operationType === 'installCollector') {
          // 安装采集器使用原接口
          const response = await getCollectorNodes({ taskId: taskIds });
          data = response?.items || [];
          taskStatus = response?.status || 'running';
          taskSummary = response?.summary || null;
        } else {
          // 启动、停止、重启使用新接口
          const response = await getCollectorOperationNodes({
            taskId: taskIds
          });
          data = response?.items || [];
          taskStatus = response?.status || 'running';
          taskSummary = response?.summary || null;
        }
      }

      const newTableData = normalizeControllerInstallRows(
        data.map((item: any, index: number) => ({
          ...item,
          cpu_architecture:
            item.cpu_architecture || item.nodeData?.cpu_architecture || '',
          id: item.id ?? index
        }))
      );
      setTableData(newTableData);

      if (refreshType === 'timer' || refreshType === 'refresh') {
        schedulePolling(newTableData);
      }

      // 如果弹窗正在查看某个节点的日志,实时更新该节点的日志（仅远程安装模式）
      // 使用 ref 获取最新值，避免闭包问题
      const viewingNode = currentViewingNodeRef.current;
      if (viewingNode && installMethod === 'remoteInstall') {
        // 使用 task_node_id、node_id 或 ip 来匹配节点，因为 id 是动态生成的 index
        const currentTaskNodeId = viewingNode.task_node_id;
        const currentNodeId = viewingNode.node_id;
        const currentIp = viewingNode.ip;
        const updatedNode = newTableData.find(
          (item) =>
            (currentTaskNodeId && item.task_node_id === currentTaskNodeId) ||
            (currentNodeId && item.node_id === currentNodeId) ||
            (currentIp && item.ip === currentIp)
        );
        if (updatedNode) {
          // 更新当前查看的节点引用
          currentViewingNodeRef.current = updatedNode;
          // 更新弹窗中的日志和节点信息
          guidance.current?.updateLogs?.(
            normalizeControllerInstallResult(updatedNode.result)?.steps || [],
            {
              ip: updatedNode.ip,
              nodeName: updatedNode.node_name
            },
            normalizeControllerInstallResult(updatedNode.result)?.installer_summary
          );
        }
      }

      // 检查是否完成并自动进入下一步
      if (isControllerOperation) {
        // 控制器操作（安装或卸载）：检查所有节点都操作成功
        const allSuccess = newTableData.every((item) =>
          ['success', 'installed'].includes(item.status || '')
        );
        if (allSuccess && newTableData.length > 0) {
          clearTimer();
          // 延迟5秒再跳转
          setTimeout(() => {
            onNext();
          }, AUTO_ADVANCE_DELAY);
        }
      } else {
        // 组件操作：根据返回的 status 和 summary 判断
        // 当 status 为 'finished' 时，停止轮询
        if (taskStatus === 'finished') {
          clearTimer();
          // 只有当 total === success 时才自动进入下一步
          if (
            taskSummary &&
            taskSummary.total === taskSummary.success &&
            taskSummary.total > 0
          ) {
            // 延迟5秒再跳转
            setTimeout(() => {
              onNext();
            }, AUTO_ADVANCE_DELAY);
          }
        }
      }
    } finally {
      setPageLoading(false);
    }
  };

  // 根据操作类型获取确认弹窗文案
  const getFinishConfirmText = useMemo(() => {
    const operationTextMap: Record<
      OperationType,
      { title: string; content1: string; content2: string }
    > = {
      installController: {
        title: t('node-manager.cloudregion.node.confirmFinishInstallTitle'),
        content1: t('node-manager.cloudregion.node.confirmFinishContent1'),
        content2: t(
          'node-manager.cloudregion.node.confirmFinishInstallContent2'
        )
      },
      uninstallController: {
        title: t('node-manager.cloudregion.node.confirmFinishUninstallTitle'),
        content1: t('node-manager.cloudregion.node.confirmFinishContent1'),
        content2: t(
          'node-manager.cloudregion.node.confirmFinishUninstallContent2'
        )
      },
      installCollector: {
        title: t('node-manager.cloudregion.node.confirmFinishInstallTitle'),
        content1: t('node-manager.cloudregion.node.confirmFinishContent1'),
        content2: t(
          'node-manager.cloudregion.node.confirmFinishInstallContent2'
        )
      },
      startCollector: {
        title: t('node-manager.cloudregion.node.confirmFinishStartTitle'),
        content1: t('node-manager.cloudregion.node.confirmFinishContent1'),
        content2: t('node-manager.cloudregion.node.confirmFinishStartContent2')
      },
      stopCollector: {
        title: t('node-manager.cloudregion.node.confirmFinishStopTitle'),
        content1: t('node-manager.cloudregion.node.confirmFinishContent1'),
        content2: t('node-manager.cloudregion.node.confirmFinishStopContent2')
      },
      restartCollector: {
        title: t('node-manager.cloudregion.node.confirmFinishRestartTitle'),
        content1: t('node-manager.cloudregion.node.confirmFinishContent1'),
        content2: t(
          'node-manager.cloudregion.node.confirmFinishRestartContent2'
        )
      }
    };
    return operationTextMap[operationType];
  }, [operationType, t]);

  const handleFinish = () => {
    const installingCount = tableData.filter(
      (item) =>
        !['error', 'success', 'installed', 'timeout'].includes(item.status)
    ).length;

    // 如果没有进行中的节点，直接返回，不需要二次确认
    if (installingCount === 0) {
      clearTimer();
      cancel();
      return;
    }

    const confirmText = getFinishConfirmText;
    Modal.confirm({
      title: confirmText.title,
      content: (
        <div>
          {confirmText.content1}
          <span style={{ color: 'var(--color-primary)' }}>
            {installingCount} {t('node-manager.cloudregion.node.nodes')}
          </span>
          {confirmText.content2}
        </div>
      ),
      icon: <ExclamationCircleFilled />,
      okText: t('node-manager.cloudregion.node.confirmFinish'),
      cancelText: t('common.cancel'),
      onOk: () => {
        clearTimer();
        cancel();
      }
    });
  };

  const handleCopyInstallCommand = async (row: ControllerInstallProgressRow) => {
    try {
      if (row.id === undefined) {
        return;
      }

      setCopyingNodeIds((prev) => [...prev, row.id]);
      const isLinux = row?.os === 'linux';
      const result = await getInstallCommand(row);
      const installCommand = result || '';
      handleCopy({
        value: installCommand,
        showSuccessMessage: false
      });
      notification.success({
        message: t('node-manager.cloudregion.node.commandCopied'),
        description: isLinux ? (
          t('node-manager.cloudregion.node.linuxCommandCopiedDesc')
        ) : (
          <div>
            <div className="mb-[12px] text-[var(--color-text-3)]">
              {t('node-manager.cloudregion.node.commandCopiedDesc')}
            </div>
            <Alert
              description={
                <span className="text-[13px] text-[var(--color-text-2)]">
                  {t('node-manager.cloudregion.node.importantNoteDesc')}
                </span>
              }
              type="warning"
            />
          </div>
        ),
        icon: <CheckCircleFilled style={{ color: 'var(--color-success)' }} />,
        placement: 'top',
        style: isLinux ? undefined : { width: 480 }
      });
    } finally {
      setCopyingNodeIds((prev) => prev.filter((id) => id !== row.id));
    }
  };

  const handleRetry = (row: ControllerInstallProgressRow) => {
    retryModalRef.current?.showModal({
      type: 'retryInstall',
      ...row,
      task_id: taskIds
    });
  };

  // 组件操作重试
  const handleCollectorRetry = async (row: ControllerInstallProgressRow) => {
    const nodeId = row.node_id || row.id;
    if (!nodeId) return;

    try {
      setRetryingNodeIds((prev) => [...prev, String(nodeId)]);

      if (operationType === 'installCollector') {
        // 安装组件重试
        if (!collectorPackageId) {
          notification.error({
            message: t('node-manager.cloudregion.node.retry'),
            description: 'Missing collector package info'
          });
          return;
        }
        await installCollector({
          collector_package: collectorPackageId,
          nodes: [String(nodeId)]
        });
      } else {
        // 启动/停止/重启组件重试
        if (!collectorId) {
          notification.error({
            message: t('node-manager.cloudregion.node.retry'),
            description: 'Missing collector info'
          });
          return;
        }
        const operationMap: Record<string, string> = {
          startCollector: 'start',
          stopCollector: 'stop',
          restartCollector: 'restart'
        };
        await batchOperationCollector({
          node_ids: [String(nodeId)],
          collector_id: collectorId,
          operation: operationMap[operationType]
        });
      }

      notification.success({
        message: t('node-manager.cloudregion.node.retrySuccess')
      });
      // 重试成功后重新启动轮询
      restartPolling();
    } finally {
      setRetryingNodeIds((prev) => prev.filter((id) => id !== String(nodeId)));
    }
  };

  const handleOperationGuidance = async (row: ControllerInstallProgressRow) => {
    operationGuidanceRef.current?.showModal({
      type: 'edit',
      form: row
    });
  };

  // 清除当前查看的节点
  const handleGuidanceClose = () => {
    currentViewingNodeRef.current = null;
  };

  return (
    <div>
      <div>
        <div className="mb-[10px] font-bold">{mergedTextConfig.listTitle}</div>
        {controllerInstallSummary && (
          <Alert
            className="mb-[12px]"
            type={
              controllerInstallSummary.error > 0 || controllerInstallSummary.timeout > 0
                ? 'warning'
                : 'info'
            }
            showIcon
            message={
              <div className="flex flex-wrap items-center gap-[8px]">
                <span>{t('node-manager.cloudregion.node.installProgressSummary')}</span>
                <Tag bordered={false} color="default">
                  {t('node-manager.cloudregion.node.summaryTotal')}: {controllerInstallSummary.total}
                </Tag>
                <Tag bordered={false} color="processing">
                  {t('node-manager.cloudregion.node.summaryRunning')}: {controllerInstallSummary.running}
                </Tag>
                <Tag bordered={false} color="success">
                  {t('node-manager.cloudregion.node.summarySuccess')}: {controllerInstallSummary.success}
                </Tag>
                <Tag bordered={false} color="error">
                  {t('node-manager.cloudregion.node.summaryFailed')}:
                  {' '}
                  {controllerInstallSummary.error + controllerInstallSummary.timeout}
                </Tag>
              </div>
            }
            description={
              <div className="pt-[4px]">
                <Progress percent={controllerInstallSummary.percent} size="small" />
              </div>
            }
          />
        )}
        <CustomTable
          scroll={{ x: 'calc(100vw - 320px)' }}
          rowKey="id"
          loading={pageLoading}
          columns={columns}
          dataSource={tableData}
        />
      </div>
      <div className="pt-[16px] flex justify-center">
        <Button type="primary" onClick={handleFinish}>
          {mergedTextConfig.finishButton}
        </Button>
      </div>
      <InstallGuidance ref={guidance} onClose={handleGuidanceClose} />
      {isInstallController && (
        <>
          <RetryInstallModal
            ref={retryModalRef}
            onSuccess={() => restartPolling()}
          />
          <OperationGuidance ref={operationGuidanceRef} />
        </>
      )}
    </div>
  );
};

export default OperationProgress;
