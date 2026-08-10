'use client';

import React from 'react';
import { Alert, Form, Input, Upload, message } from 'antd';
import type { FormInstance } from 'antd';
import ImportFileModalShell from '@/components/import-file-modal-shell';

export interface JobPlaybookUpgradeModalProps {
  open: boolean;
  confirmLoading?: boolean;
  upgradeFile: File | null;
  currentVersion?: string;
  nextVersionPlaceholder: string;
  form: FormInstance;
  onUpgradeFileChange: (file: File | null) => void;
  onConfirm: () => void;
  onCancel: () => void;
  t: (key: string) => string;
}

const JobPlaybookUpgradeModal: React.FC<JobPlaybookUpgradeModalProps> = ({
  open,
  confirmLoading = false,
  upgradeFile,
  currentVersion = 'v1.0.0',
  nextVersionPlaceholder,
  form,
  onUpgradeFileChange,
  onConfirm,
  onCancel,
  t,
}) => {
  const handleBeforeUpload = (file: File) => {
    const isValid =
      file.name.endsWith('.zip') ||
      file.name.endsWith('.tar.gz') ||
      file.name.endsWith('.tgz');

    if (!isValid) {
      message.error(t('job.onlyZipAllowed'));
      return Upload.LIST_IGNORE;
    }

    onUpgradeFileChange(file);
    return false;
  };

  return (
    <ImportFileModalShell
      title={t('job.upgradePlaybookTitle')}
      open={open}
      width={600}
      confirmLoading={confirmLoading}
      confirmText={t('job.confirm')}
      cancelText={t('job.cancel')}
      confirmDisabled={!upgradeFile}
      primaryFirst={false}
      onConfirm={onConfirm}
      onCancel={onCancel}
      beforeUploadPanel={(
        <Alert
          message={t('job.upgradeWarning')}
          type="warning"
          showIcon
          className="mb-4"
        />
      )}
      uploadProps={{
        accept: '.zip,.tar.gz,.tgz',
        maxCount: 1,
        fileList: upgradeFile
          ? [{ uid: '-1', name: upgradeFile.name, status: 'done' as const }]
          : [],
        beforeUpload: handleBeforeUpload,
        onRemove: () => {
          onUpgradeFileChange(null);
        },
        uploadText: t('job.selectNewZip'),
        uploadHint: (
          <>
            <div>{t('job.playbookArchiveLimitHint')}</div>
            <div>{t('job.playbookArchiveEntryLimitHint')}</div>
          </>
        ),
      }}
      afterUploadPanel={(
        <Form form={form} layout="vertical" colon={false} className="mt-4">
          <Form.Item label={t('job.currentVersionLabel')}>
            <Input value={currentVersion} disabled className="bg-gray-50" />
          </Form.Item>

          <Form.Item
            name="version"
            label={t('job.newVersionNumber')}
            extra={t('job.newVersionHint')}
          >
            <Input placeholder={nextVersionPlaceholder} />
          </Form.Item>
        </Form>
      )}
    />
  );
};

export default JobPlaybookUpgradeModal;
