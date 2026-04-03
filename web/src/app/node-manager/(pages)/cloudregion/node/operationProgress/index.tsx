'use client';
import React, { useEffect, useState, useRef, useMemo } from 'react';
import { Button, Tag, notification, Modal, Alert } from 'antd';
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
  const [tableData, setTableData] = useState<TableDataItem[]>([]);
  // 使用 ref 保存 currentViewingNode 的最新值，避免闭包问题
  const currentViewingNodeRef = useRef<TableDataItem | null>(null);
  const [copyingNodeIds, setCopyingNodeIds] = useState<number[]>([]);
  const [retryingNodeIds, setRetryingNodeIds] = useState<string[]>([]);

  // 是否是安装控制器操作
  const isInstallController = operationType === 'installController';
  // 是否是卸载控制器操作
  const isUninstallController = operationType === 'uninstallController';
  // 是否是控制器相关操作（安装或卸载）
  const isControllerOperation = isInstallController || isUninstallController;

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

  const columns: any = useMemo(() => {
    const baseColumns: any[] = [
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
      width: 150,
      key: 'status',
      ellipsis: true,
      render: (value: string) => {
        const status = statusMap[value as keyof typeof statusMap];
        if (!status) {
          return <span>--</span>;
        }
        return (
          <Tag
            color={status.color}
            bordered={false}
            icon={status.icon}
            className="flex items-center gap-1 w-fit"
          >
            <span>{status.text}</span>
          </Tag>
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
      render: (value: string, row: TableDataItem) => {
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
      timerRef.current = setInterval(() => {
        getNodeList('timer');
      }, 5000);
      return () => {
        clearTimer();
      };
    }
  }, [taskIds, isLoading]);

  const clearTimer = () => {
    if (timerRef.current) clearInterval(timerRef.current);
    timerRef.current = null;
  };

  // 重新启动轮询（重试成功后调用）
  const restartPolling = () => {
    clearTimer();
    getNodeList('refresh');
    timerRef.current = setInterval(() => {
      getNodeList('timer');
    }, 5000);
  };

  const checkDetail = (type: string, row: TableDataItem) => {
    const logs = row.result?.steps || [];
    currentViewingNodeRef.current = row;
    guidance.current?.showModal({
      title: t('node-manager.cloudregion.node.viewLog'),
      type,
      form: {
        logs,
        ip: row.ip,
        nodeName: row.node_name
      }
    });
  };

  const getNodeList = async (refreshType: string) => {
    try {
      setPageLoading(refreshType !== 'timer');
      let data: TableDataItem[] = [];
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
                (status: any) => status.node_id === item.node_id
              );
              return {
                ...item,
                status: statusInfo?.status || null,
                result: statusInfo?.result || null
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

      const newTableData = data.map((item: TableDataItem, index: number) => ({
        ...item,
        id: index
      }));
      setTableData(newTableData);

      // 如果弹窗正在查看某个节点的日志,实时更新该节点的日志（仅远程安装模式）
      // 使用 ref 获取最新值，避免闭包问题
      const viewingNode = currentViewingNodeRef.current;
      if (viewingNode && installMethod === 'remoteInstall') {
        // 使用 task_node_id、node_id 或 ip 来匹配节点，因为 id 是动态生成的 index
        const currentTaskNodeId = viewingNode.task_node_id;
        const currentNodeId = viewingNode.node_id;
        const currentIp = viewingNode.ip;
        const updatedNode: any = newTableData.find(
          (item: TableDataItem) =>
            (currentTaskNodeId && item.task_node_id === currentTaskNodeId) ||
            (currentNodeId && item.node_id === currentNodeId) ||
            (currentIp && item.ip === currentIp)
        );
        if (updatedNode) {
          // 更新当前查看的节点引用
          currentViewingNodeRef.current = updatedNode;
          // 更新弹窗中的日志和节点信息
          guidance.current?.updateLogs?.(updatedNode.result?.steps || [], {
            ip: updatedNode.ip,
            nodeName: updatedNode.node_name
          });
        }
      }

      // 检查是否完成并自动进入下一步
      if (isControllerOperation) {
        // 控制器操作（安装或卸载）：检查所有节点都操作成功
        const allSuccess = newTableData.every((item: TableDataItem) =>
          ['success', 'installed'].includes(item.status)
        );
        if (allSuccess && newTableData.length > 0) {
          clearTimer();
          // 延迟2秒再跳转
          setTimeout(() => {
            onNext();
          }, 2000);
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
            // 延迟2秒再跳转
            setTimeout(() => {
              onNext();
            }, 2000);
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

  const handleCopyInstallCommand = async (row: any) => {
    try {
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

  const handleRetry = (row: TableDataItem) => {
    retryModalRef.current?.showModal({
      type: 'retryInstall',
      ...row,
      task_id: taskIds
    });
  };

  // 组件操作重试
  const handleCollectorRetry = async (row: TableDataItem) => {
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

  const handleOperationGuidance = async (row: TableDataItem) => {
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
