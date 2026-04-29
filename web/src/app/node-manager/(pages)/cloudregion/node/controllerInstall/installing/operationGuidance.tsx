'use client';

import { useState, forwardRef, useImperativeHandle } from 'react';
import { Alert, message } from 'antd';
import OperateDrawer from '@/app/node-manager/components/operate-drawer';
import { ModalRef } from '@/app/node-manager/types';
import {
  InstallerArtifactMetadata,
  InstallerManifest,
  OperationGuidanceProps
} from '@/app/node-manager/types/controller';
import { useTranslation } from '@/utils/i18n';
import { useHandleCopy } from '@/app/node-manager/hooks';
import useControllerApi from '@/app/node-manager/api/useControllerApi';
import { useAuth } from '@/context/auth';
import axios from 'axios';
import {
  LinuxOperationGuidanceSection,
  WindowsOperationGuidanceSection
} from './operationGuidanceSections';

const OperationGuidance = forwardRef<ModalRef>(({}, ref) => {
  const { t } = useTranslation();
  const { handleCopy } = useHandleCopy();
  const { getInstallCommand, getInstallerManifest } = useControllerApi();
  const authContext = useAuth();
  const token = authContext?.token || null;
  const [visible, setVisible] = useState<boolean>(false);
  const [loading, setLoading] = useState<boolean>(false);
  const [downloadLoading, setDownloadLoading] = useState<boolean>(false);
  const [nodeInfo, setNodeInfo] = useState<OperationGuidanceProps>({
    ip: '',
    nodeName: '',
    os: '',
    installerVersion: '',
    defaultInstallerVersion: '',
    installerSession: '',
    nodeData: null
  });
  const [installerManifest, setInstallerManifest] =
    useState<InstallerManifest | null>(null);
  const [installerMetadata, setInstallerMetadata] =
    useState<InstallerArtifactMetadata | null>(null);

  useImperativeHandle(ref, () => ({
    showModal: async ({ form }) => {
      setVisible(true);
      const newNodeInfo = {
        ip: form?.ip || '',
        nodeName: form?.node_name || '',
        os: form?.os || '',
        installerVersion: '',
        defaultInstallerVersion: '',
        installerSession: '',
        nodeData: form || null
      };
      setNodeInfo(newNodeInfo);
      if (form) {
        fetchInstallerManifest(form?.os || 'windows');
        fetchInstallCommand(form);
      }
    }
  }));

  const fetchInstallerManifest = async (os: string) => {
    if (!os) return;
    try {
      const manifest = await getInstallerManifest();
      const osArtifacts = manifest?.artifacts?.[os] || {};
      const defaultArch = os === 'linux' ? 'x86_64' : 'x86_64';
      const result = osArtifacts?.[defaultArch] || Object.values(osArtifacts)[0] || null;
      setInstallerManifest(manifest || null);
      setNodeInfo((prev) => ({
        ...prev,
        installerVersion: result?.version || '',
        defaultInstallerVersion: manifest?.default_version || ''
      }));
      setInstallerMetadata(result || null);
    } catch {
      setInstallerManifest(null);
      setInstallerMetadata(null);
    }
  };

  const fetchInstallCommand = async (nodeData: any) => {
    if (!nodeData) return;
    setLoading(true);
    try {
      const result = await getInstallCommand(nodeData);
      setNodeInfo((prev) => ({
        ...prev,
        installerSession: result || ''
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
      value: nodeInfo.installerSession || ''
    });
  };

  const handleCopyDebugValue = (value: string) => {
    handleCopy({ value });
  };

  const handleDownload = async () => {
    try {
      setDownloadLoading(true);
      const response = await axios({
        url:
          installerMetadata?.download_url ||
          '/api/proxy/node_mgmt/api/installer/windows/download/',
        method: 'GET',
        responseType: 'blob',
        headers: {
          Authorization: `Bearer ${token}`
        }
      });
      // 创建Blob对象
      const blob = new Blob([response.data], {
        type: response.headers['content-type'] || 'application/zip'
      });
      // 尝试从响应头获取文件名
      const contentDisposition = response.headers['content-disposition'];
      let filename =
        installerMetadata?.filename || 'bk_controller_installer.exe';
      if (contentDisposition) {
        // 优先匹配 filename*=UTF-8''xxx 格式
        let filenameMatch = contentDisposition.match(/filename\*=UTF-8''(.+)/i);
        if (filenameMatch?.[1]) {
          filename = decodeURIComponent(filenameMatch[1]);
        } else {
          // 匹配 filename="xxx" 或 filename=xxx 格式
          filenameMatch = contentDisposition.match(
            /filename="([^"]+)"|filename=([^;\s]+)/i
          );
          if (filenameMatch) {
            filename = filenameMatch[1] || filenameMatch[2];
          }
        }
      }
      // 创建下载链接
      const url = URL.createObjectURL(blob);
      const link = document.createElement('a');
      link.href = url;
      link.download = filename;
      document.body.appendChild(link);
      link.click();
      document.body.removeChild(link);
      URL.revokeObjectURL(url);
      //   message.success(t('node-manager.cloudregion.node.downloadSuccess'));
    } catch {
      message.error(t('node-manager.cloudregion.node.downloadFailed'));
    } finally {
      setDownloadLoading(false);
    }
  };

  const isLinux = nodeInfo.os === 'linux';

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
          <span className="text-[12px] text-[var(--color-text-3)] ml-[16px]">
            {t('node-manager.cloudregion.node.installerVersion')}：
          </span>
          <span className="text-[12px]">
            {nodeInfo.installerVersion || '--'}
          </span>
          <span className="text-[12px] text-[var(--color-text-3)] ml-[16px]">
            {t('node-manager.cloudregion.node.defaultInstallerVersion')}：
          </span>
          <span className="text-[12px]">
            {nodeInfo.defaultInstallerVersion || '--'}
          </span>
        </div>
      }
    >
      <div className="p-[16px]">
        {isLinux ? (
          <LinuxOperationGuidanceSection
            loading={loading}
            downloadLoading={downloadLoading}
            installerSession={nodeInfo.installerSession || ''}
            installerMetadata={installerMetadata}
            installerManifest={installerManifest}
            onDownload={handleDownload}
            onCopy={handleCopyCommand}
            onCopyDebugValue={handleCopyDebugValue}
          />
        ) : (
          <WindowsOperationGuidanceSection
            loading={loading}
            downloadLoading={downloadLoading}
            installerSession={nodeInfo.installerSession || ''}
            installerMetadata={installerMetadata}
            installerManifest={installerManifest}
            onDownload={handleDownload}
            onCopy={handleCopyCommand}
            onCopyDebugValue={handleCopyDebugValue}
          />
        )}

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
