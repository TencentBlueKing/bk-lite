'use client';

import { useState, forwardRef, useImperativeHandle } from 'react';
import { Button, Alert } from 'antd';
import { DownloadOutlined } from '@ant-design/icons';
import OperateDrawer from '@/app/node-manager/components/operate-drawer';
import { ModalRef } from '@/app/node-manager/types';
import { OperationGuidanceProps } from '@/app/node-manager/types/controller';
import { useTranslation } from '@/utils/i18n';
import { useHandleCopy } from '@/app/node-manager/hooks';
import CodeEditor from '@/app/node-manager/components/codeEditor';
import useControllerApi from '@/app/node-manager/api/useControllerApi';

const OperationGuidance = forwardRef<ModalRef>(({}, ref) => {
  const { t } = useTranslation();
  const { handleCopy } = useHandleCopy();
  const { getInstallCommand } = useControllerApi();
  const [visible, setVisible] = useState<boolean>(false);
  const [loading, setLoading] = useState<boolean>(false);
  const [nodeInfo, setNodeInfo] = useState<OperationGuidanceProps>({
    ip: '',
    nodeName: '',
    installCommand: '',
    downloadUrl: '',
    nodeData: null,
  });

  useImperativeHandle(ref, () => ({
    showModal: async ({ form }) => {
      setVisible(true);
      const newNodeInfo = {
        ip: form?.ip || '',
        nodeName: form?.node_name || '',
        installCommand: '',
        downloadUrl: form?.downloadUrl || '',
        nodeData: form || null,
      };
      setNodeInfo(newNodeInfo);
      if (form) {
        fetchInstallCommand(form);
      }
    },
  }));

  const fetchInstallCommand = async (nodeData: any) => {
    if (!nodeData) return;
    setLoading(true);
    try {
      const result = await getInstallCommand(nodeData);
      setNodeInfo((prev) => ({
        ...prev,
        installCommand: result || '',
      }));
    } finally {
      setLoading(false);
    }
  };

  const handleCancel = () => {
    setVisible(false);
  };

  const handleCopyCommand = () => {
    handleCopy({
      value: nodeInfo.installCommand || '',
    });
  };

  const handleDownload = () => {
    // 创建一个隐藏的 a 标签来触发下载
    const link = document.createElement('a');
    link.href = nodeInfo.downloadUrl;
    link.download = ''; // 浏览器会使用服务器提供的文件名
    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);
  };

  return (
    <OperateDrawer
      width={700}
      title={t('node-manager.cloudregion.node.operationGuidance')}
      visible={visible}
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
        {/* 步骤1: 下载安装包 */}
        <div className="mb-[24px] p-[16px] bg-[var(--color-fill-1)] rounded-[8px]">
          <div className="flex items-center gap-2 mb-[16px]">
            <div className="flex items-center justify-center w-[24px] h-[24px] bg-[var(--color-primary)] text-white rounded-full text-[14px] font-medium">
              1
            </div>
            <span className="text-[14px] font-medium">
              {t('node-manager.cloudregion.node.downloadPackageStep')}
            </span>
          </div>
          <div className="ml-[32px]">
            <Button
              type="primary"
              icon={<DownloadOutlined />}
              disabled={!nodeInfo.downloadUrl}
              onClick={handleDownload}
            >
              {t('node-manager.cloudregion.node.clickDownloadPackage')}
              {/* (controller_v2.3.5_windows_x64.zip) */}
            </Button>
          </div>
        </div>

        {/* 步骤2: 上传安装包 */}
        <div className="mb-[24px] p-[16px] bg-[var(--color-fill-1)] rounded-[8px]">
          <div className="flex items-center gap-2 mb-[16px]">
            <div className="flex items-center justify-center w-[24px] h-[24px] bg-[var(--color-primary)] text-white rounded-full text-[14px] font-medium">
              2
            </div>
            <span className="text-[14px] font-medium">
              {t('node-manager.cloudregion.node.uploadPackageStep')}
            </span>
          </div>
          <div className="ml-[32px]">
            <div className="text-[12px] text-[var(--color-text-3)] mb-[12px]">
              {t('node-manager.cloudregion.node.uploadPackageDesc')}
            </div>
            <Alert
              message={t('node-manager.cloudregion.node.uploadPackageNote')}
              type="info"
              showIcon
            />
          </div>
        </div>

        {/* 步骤3: 运行安装包 */}
        <div className="mb-[24px] p-[16px] bg-[var(--color-fill-1)] rounded-[8px]">
          <div className="flex items-center gap-2 mb-[16px]">
            <div className="flex items-center justify-center w-[24px] h-[24px] bg-[var(--color-primary)] text-white rounded-full text-[14px] font-medium">
              3
            </div>
            <span className="text-[14px] font-medium">
              {t('node-manager.cloudregion.node.runPackageStep')}
            </span>
          </div>
          <div className="ml-[32px]">
            <div className="text-[12px] text-[var(--color-text-3)] mb-[12px]">
              {t('node-manager.cloudregion.node.runPackageDesc')}
            </div>
            <div className="mb-[12px]">
              <div className="flex items-center justify-between mb-[8px]">
                <span className="text-[14px] text-[var(--color-text-2)]">
                  {t('node-manager.cloudregion.node.installParams')}
                </span>
                <Button
                  type="link"
                  className="p-0"
                  size="small"
                  onClick={handleCopyCommand}
                >
                  {t('common.copy')}
                </Button>
              </div>
              <CodeEditor
                value={nodeInfo.installCommand || ''}
                width="100%"
                height="120px"
                mode="powershell"
                theme="monokai"
                name="install-command-editor"
                readOnly
                loading={loading}
              />
            </div>
          </div>
        </div>

        {/* 重要提示 */}
        <Alert
          message={t('node-manager.cloudregion.node.importantNote')}
          description={t('node-manager.cloudregion.node.importantNoteDesc')}
          type="warning"
          showIcon
          className="mb-[16px]"
        />
      </div>
    </OperateDrawer>
  );
});

OperationGuidance.displayName = 'OperationGuidance';
export default OperationGuidance;
