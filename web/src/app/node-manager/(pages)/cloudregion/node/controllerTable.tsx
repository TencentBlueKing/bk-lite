'use client';
import React, { useEffect, useState, useRef, useMemo } from 'react';
import { Button, Popconfirm } from 'antd';
import useApiClient from '@/utils/request';
import { useTranslation } from '@/utils/i18n';
import { ModalRef, TableDataItem } from '@/app/node-manager/types';
import { ControllerInstallProps } from '@/app/node-manager/types/cloudregion';
import controllerInstallSyle from './index.module.scss';
import { ArrowLeftOutlined, ReloadOutlined } from '@ant-design/icons';
import {
  OPERATE_SYSTEMS,
  useInstallMap,
} from '@/app/node-manager/constants/cloudregion';
import { useGroupNames } from '@/app/node-manager/hooks/node';
import CustomTable from '@/components/custom-table';
import useApiCloudRegion from '@/app/node-manager/api/cloudregion';
import InstallGuidance from './installGuidance';

const ControllerTable: React.FC<ControllerInstallProps> = ({
  cancel,
  config,
}) => {
  const { t } = useTranslation();
  const { isLoading } = useApiClient();
  const { getControllerNodes, getCollectorNodes } = useApiCloudRegion();
  const installMay = useInstallMap();
  const { showGroupNames } = useGroupNames();
  const guidance = useRef<ModalRef>(null);
  const timerRef = useRef<NodeJS.Timeout | null>(null);
  const [pageLoading, setPageLoading] = useState<boolean>(false);
  const [tableData, setTableData] = useState<TableDataItem[]>([]);

  const columns: any = useMemo(() => {
    return [
      {
        title: t('node-manager.cloudregion.node.ipAdrress'),
        dataIndex: 'ip',
        width: 100,
        key: 'ip',
      },
      {
        title: t('node-manager.cloudregion.node.operateSystem'),
        dataIndex: 'os',
        width: 100,
        key: 'os',
        ellipsis: true,
        render: (value: string) => {
          return (
            <>
              {OPERATE_SYSTEMS.find((item) => item.value === value)?.label ||
                '--'}
            </>
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
        title: t(
          `node-manager.cloudregion.node.${
            config.type.includes('Collector') ? 'collector' : 'sidecar'
          }`
        ),
        dataIndex: 'result',
        width: 100,
        key: 'result',
        ellipsis: true,
        render: (value: Record<string, string>) => {
          const installStatus =
            config.type === 'uninstallController'
              ? `${value?.status}Uninstall`
              : value?.status;
          return (
            <span
              style={{
                color:
                  installMay[installStatus]?.color || 'var(--ant-color-text)',
              }}
            >
              {installMay[installStatus]?.text || '--'}
            </span>
          );
        },
      },
      {
        title: t('common.actions'),
        dataIndex: 'action',
        width: 60,
        fixed: 'right',
        key: 'action',
        render: (value: string, row: TableDataItem) => {
          return (
            <Button
              type="link"
              disabled={row.result?.status !== 'failed'}
              onClick={() => checkDetail('remoteInstall', row)}
            >
              {t('node-manager.cloudregion.node.viewLog')}
            </Button>
          );
        },
      },
    ];
  }, [config.type]);

  useEffect(() => {
    if (isLoading) return;
    clearTimer();
    if (config.taskId && config.type) {
      getNodeList('refresh');
      timerRef.current = setInterval(() => {
        getNodeList('timer');
      }, 5000);
      return () => {
        clearTimer();
      };
    }
  }, [config.taskId, config.type, isLoading]);

  const clearTimer = () => {
    if (timerRef.current) clearInterval(timerRef.current);
    timerRef.current = null;
  };

  const checkDetail = (type: string, row: TableDataItem) => {
    let message = '';
    if (row.result?.status === 'failed') {
      message += row.result?.message;
    }
    guidance.current?.showModal({
      title: t('node-manager.cloudregion.node.log'),
      type,
      form: { message: message || '--' },
    });
  };

  const getNodeList = async (refreshType: string) => {
    try {
      setPageLoading(refreshType !== 'timer');
      const request = config.type.includes('Collector')
        ? getCollectorNodes
        : getControllerNodes;
      const data = await request({ taskId: config.taskId });
      setTableData(
        data.map((item: TableDataItem, index: number) => ({
          id: index,
          ...item,
        }))
      );
    } finally {
      setPageLoading(false);
    }
  };

  return (
    <div className={controllerInstallSyle.controllerInstall}>
      <div className={controllerInstallSyle.title}>
        <Popconfirm
          title={t('common.prompt')}
          description={t('node-manager.cloudregion.node.installingTips')}
          okText={t('common.confirm')}
          cancelText={t('common.cancel')}
          onConfirm={cancel}
        >
          <ArrowLeftOutlined className="text-[var(--color-primary)] text-[20px] cursor-pointer mr-[10px]" />
        </Popconfirm>
        <span>{t('node-manager.cloudregion.node.autoInstall')}</span>
      </div>
      <div className={controllerInstallSyle.table}>
        <div className="flex justify-end mb-[16px]">
          <ReloadOutlined onClick={() => getNodeList('refresh')} />
        </div>
        <CustomTable
          rowKey="id"
          loading={pageLoading}
          columns={columns}
          dataSource={tableData}
        />
      </div>
      <InstallGuidance ref={guidance} />
    </div>
  );
};

export default ControllerTable;
