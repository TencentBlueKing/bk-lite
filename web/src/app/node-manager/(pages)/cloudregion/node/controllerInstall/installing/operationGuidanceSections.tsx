'use client';

import { useState } from 'react';
import { Alert, Button } from 'antd';
import { DownloadOutlined } from '@ant-design/icons';
import CodeEditor from '@/app/node-manager/components/codeEditor';
import { useTranslation } from '@/utils/i18n';
import { InstallerArtifactMetadata, InstallerManifest } from '@/app/node-manager/types/controller';

interface SharedProps {
  loading: boolean;
  copying: boolean;
  downloadLoading: boolean;
  installerSession: string;
  installerMetadata: InstallerArtifactMetadata | null;
  installerManifest: InstallerManifest | null;
  onDownload: () => void;
  onCopy: () => void;
  onCopyDebugValue: (value: string) => void;
}

function DownloadInfo({
  installerMetadata,
  installerManifest,
  onCopyDebugValue,
}: Pick<SharedProps, 'installerMetadata' | 'installerManifest' | 'onCopyDebugValue'>) {
  const { t } = useTranslation();
  const [expanded, setExpanded] = useState(false);
  const artifactJson = JSON.stringify(installerMetadata || {}, null, 2);

  const renderCopyRow = (label: string, value: string) => (
    <div className="flex items-start justify-between gap-[12px]">
      <div className="flex-1 break-all">
        <span className="text-[var(--color-text-3)]">{label}：</span>
        {value || '--'}
      </div>
      {value ? (
        <Button
          type="link"
          className="px-0 h-auto"
          size="small"
          onClick={() => onCopyDebugValue(value)}
        >
          {t('common.copy')}
        </Button>
      ) : null}
    </div>
  );

  return (
    <div className="mb-[12px]">
      <Alert
        message={`${t('node-manager.cloudregion.node.installerFilename')}：${installerMetadata?.filename || '--'}`}
        description={`${t('node-manager.cloudregion.node.defaultInstallerVersion')}：${installerManifest?.default_version || '--'}`}
        type="info"
        showIcon
      />
      <Button
        type="link"
        className="px-0 mt-[8px]"
        size="small"
        onClick={() => setExpanded((prev) => !prev)}
      >
        {expanded
          ? t('node-manager.cloudregion.node.hideInstallerDebugInfo')
          : t('node-manager.cloudregion.node.showInstallerDebugInfo')}
      </Button>
      {expanded && (
        <div className="mt-[8px] rounded-[8px] bg-[var(--color-fill-1)] p-[12px] text-[12px] text-[var(--color-text-2)] break-all space-y-[6px]">
          {renderCopyRow(
            t('node-manager.cloudregion.node.installerPlatform'),
            installerMetadata?.os || ''
          )}
          {renderCopyRow(
            t('node-manager.cloudregion.node.installerVersion'),
            installerMetadata?.version || ''
          )}
          {renderCopyRow(
            t('node-manager.cloudregion.node.installerDownloadUrl'),
            installerMetadata?.download_url || ''
          )}
          {renderCopyRow(
            t('node-manager.cloudregion.node.installerAliasObjectKey'),
            installerMetadata?.alias_object_key || ''
          )}
          {renderCopyRow(
            t('node-manager.cloudregion.node.installerObjectKey'),
            installerMetadata?.object_key || ''
          )}
          <div className="pt-[4px]">
            <Button
              type="link"
              className="px-0"
              size="small"
              onClick={() => onCopyDebugValue(artifactJson)}
            >
              {t('node-manager.cloudregion.node.copyArtifactJson')}
            </Button>
          </div>
        </div>
      )}
    </div>
  );
}

function SessionEditor({
  installerSession,
  loading,
  copying,
  onCopy,
}: Pick<SharedProps, 'installerSession' | 'loading' | 'copying' | 'onCopy'>) {
  const { t } = useTranslation();

  return (
    <div className="mb-[12px]">
      <div className="flex items-center justify-between mb-[8px]">
        <span className="text-[14px] text-[var(--color-text-2)]">
          {t('node-manager.cloudregion.node.installerSession')}
        </span>
        <Button
          type="link"
          className="p-0"
          size="small"
          loading={copying}
          disabled={loading || !installerSession.trim()}
          onClick={onCopy}
        >
          {t('common.copy')}
        </Button>
      </div>
      <CodeEditor
        value={installerSession || ''}
        width="100%"
        height="120px"
        mode="powershell"
        theme="monokai"
        name="install-command-editor"
        readOnly
        loading={loading}
      />
    </div>
  );
}

export function WindowsOperationGuidanceSection({
  loading,
  copying,
  downloadLoading,
  installerSession,
  installerMetadata,
  installerManifest,
  onDownload,
  onCopy,
  onCopyDebugValue,
}: SharedProps) {
  const { t } = useTranslation();

  return (
    <>
      <div className="mb-[24px] p-[16px] bg-[var(--color-fill-1)] rounded-[8px]">
        <div className="flex items-center gap-2 mb-[16px]">
          <div className="flex items-center justify-center w-[24px] h-[24px] bg-[var(--color-primary)] text-white rounded-full text-[14px] font-medium">1</div>
          <span className="text-[14px] font-medium">{t('node-manager.cloudregion.node.downloadPackageStep')}</span>
        </div>
        <div className="ml-[32px]">
          <div className="text-[12px] text-[var(--color-text-3)] mb-[12px]">
            {t('node-manager.cloudregion.node.windowsInstallerNote')}
          </div>
          <DownloadInfo installerMetadata={installerMetadata} installerManifest={installerManifest} onCopyDebugValue={onCopyDebugValue} />
          <Button type="primary" icon={<DownloadOutlined />} loading={downloadLoading} onClick={onDownload}>
            {t('node-manager.cloudregion.node.clickDownloadPackage')}
          </Button>
        </div>
      </div>

      <div className="mb-[24px] p-[16px] bg-[var(--color-fill-1)] rounded-[8px]">
        <div className="flex items-center gap-2 mb-[16px]">
          <div className="flex items-center justify-center w-[24px] h-[24px] bg-[var(--color-primary)] text-white rounded-full text-[14px] font-medium">2</div>
          <span className="text-[14px] font-medium">{t('node-manager.cloudregion.node.uploadPackageStep')}</span>
        </div>
        <div className="ml-[32px]">
          <div className="text-[12px] text-[var(--color-text-3)] mb-[12px]">
            {t('node-manager.cloudregion.node.uploadPackageDesc')}
          </div>
          <Alert message={t('node-manager.cloudregion.node.uploadPackageNote')} type="info" showIcon />
        </div>
      </div>

      <div className="mb-[24px] p-[16px] bg-[var(--color-fill-1)] rounded-[8px]">
        <div className="flex items-center gap-2 mb-[16px]">
          <div className="flex items-center justify-center w-[24px] h-[24px] bg-[var(--color-primary)] text-white rounded-full text-[14px] font-medium">3</div>
          <span className="text-[14px] font-medium">{t('node-manager.cloudregion.node.runPackageStep')}</span>
        </div>
        <div className="ml-[32px]">
          <div className="text-[12px] text-[var(--color-text-3)] mb-[12px]">
            {t('node-manager.cloudregion.node.runPackageDesc')}
          </div>
          <SessionEditor installerSession={installerSession} loading={loading} copying={copying} onCopy={onCopy} />
        </div>
      </div>
    </>
  );
}

export function LinuxOperationGuidanceSection({
  loading,
  copying,
  downloadLoading,
  installerSession,
  installerMetadata,
  installerManifest,
  onDownload,
  onCopy,
  onCopyDebugValue,
}: SharedProps) {
  const { t } = useTranslation();

  return (
    <>
      <div className="mb-[24px] p-[16px] bg-[var(--color-fill-1)] rounded-[8px]">
        <div className="flex items-center gap-2 mb-[16px]">
          <div className="flex items-center justify-center w-[24px] h-[24px] bg-[var(--color-primary)] text-white rounded-full text-[14px] font-medium">1</div>
          <span className="text-[14px] font-medium">{t('node-manager.cloudregion.node.downloadPackageStep')}</span>
        </div>
        <div className="ml-[32px]">
          <div className="text-[12px] text-[var(--color-text-3)] mb-[12px]">
            {t('node-manager.cloudregion.node.linuxDownloadPackageDesc')}
          </div>
          <DownloadInfo installerMetadata={installerMetadata} installerManifest={installerManifest} onCopyDebugValue={onCopyDebugValue} />
          <Button type="primary" icon={<DownloadOutlined />} loading={downloadLoading} onClick={onDownload}>
            {t('node-manager.cloudregion.node.clickDownloadPackage')}
          </Button>
        </div>
      </div>

      <div className="mb-[24px] p-[16px] bg-[var(--color-fill-1)] rounded-[8px]">
        <div className="flex items-center gap-2 mb-[16px]">
          <div className="flex items-center justify-center w-[24px] h-[24px] bg-[var(--color-primary)] text-white rounded-full text-[14px] font-medium">2</div>
          <span className="text-[14px] font-medium">{t('node-manager.cloudregion.node.runCommandStep')}</span>
        </div>
        <div className="ml-[32px]">
          <div className="text-[12px] text-[var(--color-text-3)] mb-[12px]">
            {t('node-manager.cloudregion.node.linuxRunCommandDesc')}
          </div>
        </div>
      </div>

      <div className="mb-[24px] p-[16px] bg-[var(--color-fill-1)] rounded-[8px]">
        <div className="flex items-center gap-2 mb-[16px]">
          <div className="flex items-center justify-center w-[24px] h-[24px] bg-[var(--color-primary)] text-white rounded-full text-[14px] font-medium">3</div>
          <span className="text-[14px] font-medium">{t('node-manager.cloudregion.node.copyInstallCommand')}</span>
        </div>
        <div className="ml-[32px]">
          <div className="text-[12px] text-[var(--color-text-3)] mb-[12px]">
            {t('node-manager.cloudregion.node.commandCopiedDesc')}
          </div>
          <SessionEditor installerSession={installerSession} loading={loading} copying={copying} onCopy={onCopy} />
        </div>
      </div>
    </>
  );
}
