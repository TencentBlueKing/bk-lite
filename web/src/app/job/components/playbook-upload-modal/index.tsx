'use client';

import React from 'react';
import { Button, Form, Input, Upload, message } from 'antd';
import type { FormInstance } from 'antd';
import { DownloadOutlined } from '@ant-design/icons';
import GroupTreeSelect from '@/components/group-tree-select';
import ImportFileModalShell from '@/components/import-file-modal-shell';

export interface JobPlaybookUploadModalProps {
  open: boolean;
  confirmLoading?: boolean;
  uploadFile: File | null;
  form: FormInstance;
  onUploadFileChange: (file: File | null) => void;
  onConfirm: () => void;
  onCancel: () => void;
  onDownloadTemplate: () => void;
  t: (key: string) => string;
}

const JobPlaybookUploadModal: React.FC<JobPlaybookUploadModalProps> = ({
  open,
  confirmLoading = false,
  uploadFile,
  form,
  onUploadFileChange,
  onConfirm,
  onCancel,
  onDownloadTemplate,
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

    onUploadFileChange(file);
    return false;
  };

  return (
    <ImportFileModalShell
      title={t('job.uploadPlaybook')}
      open={open}
      width={600}
      confirmLoading={confirmLoading}
      confirmText={t('job.confirmUpload')}
      cancelText={t('job.cancel')}
      confirmDisabled={!uploadFile}
      onConfirm={onConfirm}
      onCancel={onCancel}
      primaryFirst={false}
      uploadProps={{
        accept: '.zip,.tar.gz,.tgz',
        maxCount: 1,
        fileList: uploadFile
          ? [{ uid: '-1', name: uploadFile.name, status: 'done' as const }]
          : [],
        beforeUpload: handleBeforeUpload,
        onRemove: () => {
          onUploadFileChange(null);
        },
        uploadText: t('job.dragUploadText'),
        uploadHint: (
          <>
            <div>{t('job.dragUploadHint')}</div>
            <div>{t('job.playbookArchiveLimitHint')}</div>
            <div>{t('job.playbookArchiveEntryLimitHint')}</div>
          </>
        ),
        children: (
          <Button className="mt-[10px]" icon={<DownloadOutlined />} onClick={onDownloadTemplate}>
            {t('job.downloadPlaybookTemplate')}
          </Button>
        ),
      }}
      afterUploadPanel={
        <Form form={form} layout="vertical" colon={false} className="mt-4">
          <Form.Item name="version" label={t('job.versionOptional')}>
            <Input placeholder={t('job.versionPlaceholder')} />
          </Form.Item>

          <Form.Item
            name="team"
            label={t('job.organization')}
            rules={[{ required: true, message: t('job.organizationPlaceholder') }]}
          >
            <GroupTreeSelect multiple placeholder={t('job.organizationPlaceholder')} />
          </Form.Item>
        </Form>
      }
    />
  );
};

export default JobPlaybookUploadModal;
