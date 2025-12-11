'use client';

import React, { useState, forwardRef, useImperativeHandle } from 'react';
import { Steps, Tag } from 'antd';
import {
  CheckCircleFilled,
  CloseCircleFilled,
  LoadingOutlined,
} from '@ant-design/icons';
import OperateDrawer from '@/app/node-manager/components/operate-drawer';
import { ModalRef } from '@/app/node-manager/types';
import { LogStep, StatusConfig } from '@/app/node-manager/types/controller';
import { useTranslation } from '@/utils/i18n';
import { useLocalizedTime } from '@/hooks/useLocalizedTime';

const InstallGuidance = forwardRef<ModalRef>(({}, ref) => {
  const { t } = useTranslation();
  const { convertToLocalizedTime } = useLocalizedTime();
  const [groupVisible, setGroupVisible] = useState<boolean>(false);
  const [title, setTitle] = useState<string>('');
  const [logs, setLogs] = useState<LogStep[]>([]);
  const [nodeInfo, setNodeInfo] = useState({ ip: '', nodeName: '' });

  useImperativeHandle(ref, () => ({
    showModal: ({ title, form }) => {
      setGroupVisible(true);
      setTitle(title || '');
      setLogs(form?.logs || []);
      setNodeInfo({
        ip: form?.ip || '',
        nodeName: form?.nodeName || '',
      });
    },
    updateLogs: (newLogs: LogStep[]) => {
      setLogs(newLogs);
    },
  }));

  const handleCancel = () => {
    setGroupVisible(false);
  };

  // 统一的状态配置方法
  const getStatusConfig = (status: string): StatusConfig => {
    const statusConfigs: Record<string, StatusConfig> = {
      success: {
        text: t('node-manager.cloudregion.node.statusCompleted'),
        tagColor: 'success',
        borderColor: '#52c41a',
        stepStatus: 'finish',
        icon: <CheckCircleFilled style={{ color: '#52c41a' }} />,
      },
      error: {
        text: t('node-manager.cloudregion.node.failed'),
        tagColor: 'error',
        borderColor: '#ff4d4f',
        stepStatus: 'finish',
        icon: <CloseCircleFilled style={{ color: '#ff4d4f' }} />,
      },
      running: {
        text: t('node-manager.cloudregion.node.statusRunning'),
        tagColor: 'processing',
        borderColor: 'var(--color-primary)',
        stepStatus: 'finish',
        icon: <LoadingOutlined />,
      },
    };

    return (
      statusConfigs[status] || {
        text: status,
        tagColor: 'processing' as const,
        borderColor: 'var(--color-primary)',
        stepStatus: 'finish' as const,
        icon: <LoadingOutlined />,
      }
    );
  };

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
            current={logs.length}
            items={logs.map((log) => {
              const statusConfig = getStatusConfig(log.status);
              return {
                status: statusConfig.stepStatus,
                icon: statusConfig.icon,
                title: (
                  <div className="flex items-center justify-between">
                    <span className="text-[14px] font-medium">
                      {log.action}
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
                        borderLeftColor: statusConfig.borderColor,
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
                        {log.message}
                      </div>
                    </div>
                  </div>
                ),
              };
            })}
          />
        </div>
      </OperateDrawer>
    </div>
  );
});
InstallGuidance.displayName = 'InstallGuidance';
export default InstallGuidance;
