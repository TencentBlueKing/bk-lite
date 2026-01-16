'use client';
import React, { useEffect, useState, useRef, useMemo } from 'react';
import { Button, Tag, notification, Modal, Alert } from 'antd';
import {
  CheckCircleOutlined,
  CheckCircleFilled,
  CloseCircleOutlined,
  ClockCircleOutlined,
  SyncOutlined,
  ExclamationCircleFilled,
} from '@ant-design/icons';
import useApiClient from '@/utils/request';
import { useTranslation } from '@/utils/i18n';
import { ModalRef, TableDataItem } from '@/app/node-manager/types';
import { InstallingProps } from '@/app/node-manager/types/controller';
import { OPERATE_SYSTEMS } from '@/app/node-manager/constants/cloudregion';
import { useGroupNames } from '@/app/node-manager/hooks/node';
import { useHandleCopy } from '@/app/node-manager/hooks';
import CustomTable from '@/components/custom-table';
import useNodeManagerApi from '@/app/node-manager/api';
import useControllerApi from '@/app/node-manager/api/useControllerApi';
import InstallGuidance from './installGuidance';
import RetryInstallModal from './retryInstallModal';
import OperationGuidance from './operationGuidance';
import Icon from '@/components/icon';

const Installing: React.FC<InstallingProps> = ({
  onNext,
  cancel,
  installData,
}) => {
  const { t } = useTranslation();
  const { isLoading } = useApiClient();
  const { handleCopy } = useHandleCopy();
  const { getControllerNodes } = useNodeManagerApi();
  const { getManualInstallStatus, getInstallCommand } = useControllerApi();
  const { showGroupNames } = useGroupNames();
  const guidance = useRef<ModalRef>(null);
  const retryModalRef = useRef<ModalRef>(null);
  const operationGuidanceRef = useRef<ModalRef>(null);
  const timerRef = useRef<NodeJS.Timeout | null>(null);
  const [pageLoading, setPageLoading] = useState<boolean>(false);
  const [tableData, setTableData] = useState<TableDataItem[]>([]);
  const [currentViewingNode, setCurrentViewingNode] =
    useState<TableDataItem | null>(null);
  const [copyingNodeIds, setCopyingNodeIds] = useState<number[]>([]);

  // 安装状态映射
  const installStatusMap = useMemo(() => {
    const isManualInstall = installData?.installMethod === 'manualInstall';
    return {
      success: {
        color: 'success',
        text: t('node-manager.cloudregion.node.installSuccess'),
        icon: <CheckCircleOutlined />,
      },
      installed: {
        color: 'success',
        text: t('node-manager.cloudregion.node.installSuccess'),
        icon: <CheckCircleOutlined />,
      },
      error: {
        color: 'error',
        text: t('node-manager.cloudregion.node.installError'),
        icon: <CloseCircleOutlined />,
      },
      timeout: {
        color: 'error',
        text: t('node-manager.cloudregion.node.installTimeout'),
        icon: <ClockCircleOutlined />,
      },
      waiting: {
        color: 'processing',
        text: isManualInstall
          ? t('node-manager.cloudregion.node.waitingManual')
          : t('node-manager.cloudregion.node.remoteInstalling'),
        icon: <SyncOutlined spin />,
      },
      installing: {
        color: 'processing',
        text: t('node-manager.cloudregion.node.remoteInstalling'),
        icon: <SyncOutlined spin />,
      },
    };
  }, [t, installData?.installMethod]);

  const columns: any = useMemo(() => {
    return [
      {
        title: t('node-manager.cloudregion.node.ipAdrress'),
        dataIndex: 'ip',
        width: 100,
        key: 'ip',
      },
      {
        title: t('node-manager.cloudregion.node.nodeName'),
        dataIndex: 'node_name',
        width: 120,
        key: 'node_name',
        ellipsis: true,
        render: (value: string) => value || '--',
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
        },
      },
      {
        title: t('node-manager.cloudregion.node.organaziton'),
        dataIndex: 'organizations',
        width: 100,
        key: 'organizations',
        ellipsis: true,
        render: (value: string[]) => {
          return <>{showGroupNames(value || []) || '--'}</>;
        },
      },
      {
        title: t('node-manager.cloudregion.node.installationMethod'),
        dataIndex: 'install_way',
        width: 100,
        key: 'install_way',
        ellipsis: true,
        render: () => {
          const installWay =
            installData?.installMethod === 'manualInstall'
              ? t('node-manager.cloudregion.node.manualInstall')
              : t('node-manager.cloudregion.node.remoteInstall');
          return <>{installWay}</>;
        },
      },
      {
        title: t('node-manager.cloudregion.node.installStatus'),
        dataIndex: 'status',
        width: 150,
        key: 'status',
        ellipsis: true,
        render: (value: string) => {
          const status =
            installStatusMap[value as keyof typeof installStatusMap];
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
        },
      },
      {
        title: t('common.actions'),
        dataIndex: 'action',
        width: 170,
        fixed: 'right',
        key: 'action',
        render: (value: string, row: TableDataItem) => {
          const isManualInstall =
            installData?.installMethod === 'manualInstall';
          const isWindows = row.os === 'windows';
          return (
            <>
              {isManualInstall ? (
                <>
                  {isWindows && (
                    <Button
                      type="link"
                      className="mr-[10px]"
                      disabled
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
              ) : (
                <>
                  <Button
                    type="link"
                    onClick={() => checkDetail(installData?.installMethod, row)}
                  >
                    {t('node-manager.cloudregion.node.viewLog')}
                  </Button>
                  {['error', 'timeout'].includes(row.status) && (
                    <Button
                      type="link"
                      className="ml-[10px]"
                      onClick={() => handleRetry(row)}
                    >
                      {t('node-manager.cloudregion.node.retry')}
                    </Button>
                  )}
                </>
              )}
            </>
          );
        },
      },
    ];
  }, [installData?.installMethod, copyingNodeIds]);

  useEffect(() => {
    if (installData?.taskIds && !isLoading) {
      getNodeList('refresh');
      timerRef.current = setInterval(() => {
        getNodeList('timer');
      }, 5000);
      return () => {
        clearTimer();
      };
    }
  }, [installData?.taskIds, isLoading]);

  const clearTimer = () => {
    if (timerRef.current) clearInterval(timerRef.current);
    timerRef.current = null;
  };

  const checkDetail = (type: string, row: TableDataItem) => {
    const logs = row.result?.steps || [];
    setCurrentViewingNode(row); // 记录当前查看的节点
    guidance.current?.showModal({
      title: t('node-manager.cloudregion.node.installLog'),
      type,
      form: {
        logs,
        ip: row.ip,
        nodeName: row.node_name,
      },
    });
  };

  const getNodeList = async (refreshType: string) => {
    try {
      setPageLoading(refreshType !== 'timer');
      let data: TableDataItem[] = [];
      if (installData.installMethod === 'remoteInstall') {
        data = await getControllerNodes({ taskId: installData.taskIds });
      } else {
        const manualTaskList = installData.manualTaskList || [];
        if (manualTaskList.length > 0) {
          const statusData = await getManualInstallStatus({
            node_ids: installData.taskIds,
          });
          data = manualTaskList.map((item: TableDataItem) => {
            const statusInfo = statusData.find(
              (status: any) => status.node_id === item.node_id
            );
            return {
              ...item,
              status: statusInfo?.status || null,
              result: statusInfo?.result || null,
            };
          });
        }
      }
      const newTableData = data.map((item: TableDataItem, index: number) => ({
        ...item,
        id: index,
      }));
      setTableData(newTableData);
      // 如果弹窗正在查看某个节点的日志,实时更新该节点的日志
      if (currentViewingNode && installData.installMethod === 'remoteInstall') {
        const updatedNode = newTableData.find(
          (item: TableDataItem) => item.id === currentViewingNode.id
        );
        if (updatedNode) {
          guidance.current?.updateLogs?.(
            (updatedNode as any).result?.steps || []
          );
        }
      }
      // 检查是否所有节点都安装成功
      const allSuccess = newTableData.every((item: TableDataItem) =>
        ['success', 'installed'].includes(item.status)
      );
      if (allSuccess && newTableData.length > 0) {
        // 所有节点安装成功，清除定时器并进入第三步
        clearTimer();
        onNext();
      }
    } finally {
      setPageLoading(false);
    }
  };

  const handleFinish = () => {
    // 计算正在安装中的节点数
    const installingCount = tableData.filter(
      (item) => !['error', 'sucusess', 'installed'].includes(item.status)
    ).length;
    Modal.confirm({
      title: t('node-manager.cloudregion.node.confirmFinishTitle'),
      content: (
        <div>
          {t('node-manager.cloudregion.node.confirmFinishContent1')}
          <span style={{ color: 'var(--color-primary)' }}>
            {installingCount} {t('node-manager.cloudregion.node.nodes')}
          </span>
          {t('node-manager.cloudregion.node.confirmFinishContent2')}
        </div>
      ),
      icon: <ExclamationCircleFilled />,
      okText: t('node-manager.cloudregion.node.confirmFinish'),
      cancelText: t('common.cancel'),
      onOk: () => {
        clearTimer();
        cancel(); // 返回节点列表
      },
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
        showSuccessMessage: false,
      });
      notification.success({
        message: t('node-manager.cloudregion.node.commandCopied'),
        description: isLinux ? (
          t('node-manager.cloudregion.node.linuxCommandCopiedDesc')
        ) : (
          <div>
            <div className="mb-[12px]">
              {t('node-manager.cloudregion.node.commandCopiedDesc')}
            </div>
            <Alert
              message={t('node-manager.cloudregion.node.importantNote')}
              description={t('node-manager.cloudregion.node.importantNoteDesc')}
              type="error"
              showIcon
            />
          </div>
        ),
        icon: <CheckCircleFilled style={{ color: 'var(--color-success)' }} />,
        placement: 'top',
        style: isLinux ? undefined : { width: 480 },
      });
    } finally {
      setCopyingNodeIds((prev) => prev.filter((id) => id !== row.id));
    }
  };

  const handleRetry = (row: TableDataItem) => {
    retryModalRef.current?.showModal({
      type: 'retryInstall',
      ...row,
      task_id: installData.taskIds,
    });
  };

  const handleOperationGuidance = async (row: TableDataItem) => {
    operationGuidanceRef.current?.showModal({
      type: 'edit',
      form: row,
    });
  };

  return (
    <div>
      <div>
        <div className="mb-[10px] font-bold">
          {t('node-manager.controller.installList')}
        </div>
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
          {t('node-manager.controller.finishInstall')}
        </Button>
      </div>
      <InstallGuidance ref={guidance} />
      <RetryInstallModal
        ref={retryModalRef}
        onSuccess={() => getNodeList('refresh')}
      />
      <OperationGuidance ref={operationGuidanceRef} />
    </div>
  );
};

export default Installing;
