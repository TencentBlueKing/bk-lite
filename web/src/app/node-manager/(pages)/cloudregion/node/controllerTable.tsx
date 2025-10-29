'use client';
import React, { useEffect, useState, useRef, useMemo } from 'react';
import { Button, Popconfirm } from 'antd';
import useApiClient from '@/utils/request';
import { useTranslation } from '@/utils/i18n';
import { ModalRef, TableDataItem } from '@/app/node-manager/types';
import { ControllerInstallProps } from '@/app/node-manager/types/cloudregion';
import controllerInstallSyle from './index.module.scss';
import { ArrowLeftOutlined, ReloadOutlined } from '@ant-design/icons';
import { OPERATE_SYSTEMS } from '@/app/node-manager/constants/cloudregion';
import { useGroupNames, useInstallMap } from '@/app/node-manager/hooks/node';
import CustomTable from '@/components/custom-table';
import useNodeManagerApi from '@/app/node-manager/api';
import InstallGuidance from './installGuidance';

const ControllerTable: React.FC<ControllerInstallProps> = ({
  cancel,
  config,
}) => {
  const { t } = useTranslation();
  const { isLoading } = useApiClient();
  const { getControllerNodes, getCollectorNodes } = useNodeManagerApi();
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
        dataIndex: 'status',
        width: 100,
        key: 'status',
        ellipsis: true,
        render: (value: string) => {
          const installStatus =
            config.type === 'uninstallController' ? `${value}Uninstall` : value;
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
              disabled={row.status !== 'error'}
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
    let str = '';
    if (row.status === 'error') {
      const { steps = [] } = row.result || {};
      str = steps.reduce((pre: string, cur: TableDataItem, index: number) => {
        const { action, message } = cur || {};
        const isLast = index === steps.length - 1;
        return (pre += `${action ? action + ': ' : ''}${message}${
          isLast ? '' : '\n'
        }`);
      }, '');
    }
    guidance.current?.showModal({
      title: t('node-manager.cloudregion.node.log'),
      type,
      form: { message: str || '--' },
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
        <span>{t(`node-manager.cloudregion.node.${config.type}`)}</span>
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
