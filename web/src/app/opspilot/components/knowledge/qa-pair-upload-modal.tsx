'use client';

import React from 'react';
import { Button } from 'antd';
import type { UploadFile } from 'antd';
import ImportFileModalShell from '@/components/import-file-modal-shell';

interface UploadedFile extends File {
  uid?: string;
}

interface QAPairUploadModalProps {
  visible: boolean;
  confirmLoading: boolean;
  uploadedFiles: UploadedFile[];
  uploadingFiles: Set<string>;
  onOk: () => void;
  onCancel: () => void;
  onFileUpload: (file: File) => boolean;
  onRemoveFile: (file: UploadedFile) => void;
  onDownloadTemplate: (fileType: 'json' | 'csv') => void;
  t: (key: string) => string;
}

const QAPairUploadModal: React.FC<QAPairUploadModalProps> = ({
  visible,
  confirmLoading,
  uploadedFiles,
  uploadingFiles,
  onOk,
  onCancel,
  onFileUpload,
  onRemoveFile,
  onDownloadTemplate,
  t,
}) => {
  const fileList = uploadedFiles.map(file => {
    const fileId = file.uid || file.name;
    const isUploading = uploadingFiles.has(fileId);
    return {
      uid: fileId,
      name: file.name,
      status: isUploading ? 'uploading' as const : 'done' as const,
      percent: isUploading ? 50 : 100,
    };
  });

  const handleRemove = (file: UploadFile) => {
    onRemoveFile({ name: file.name, uid: file.uid } as UploadedFile);
  };

  return (
    <ImportFileModalShell
      title={t('common.import')}
      visible={visible}
      confirmLoading={confirmLoading}
      confirmDisabled={uploadingFiles.size > 0 || uploadedFiles.length === 0}
      onConfirm={onOk}
      onCancel={onCancel}
      confirmText={t('common.confirm')}
      cancelText={t('common.cancel')}
      uploadProps={{
        accept: 'application/json,.csv',
        beforeUpload: onFileUpload,
        onRemove: handleRemove,
        fileList,
        uploadText: t('knowledge.qaPairs.dragOrClick'),
        uploadHint: t('knowledge.qaPairs.uploadHint'),
      }}
      afterUploadPanel={
        <div className="pt-4">
          <div className="flex items-center text-xs">
            <span className="text-gray-600">{t('knowledge.qaPairs.downloadTemplate')}：</span>
            <div className="flex gap-2">
              <Button
                type="link"
                size="small"
                className="text-xs"
                onClick={() => onDownloadTemplate('json')}
              >
                JSON {t('knowledge.qaPairs.template')}
              </Button>
              <Button
                type="link"
                size="small"
                className="text-xs"
                onClick={() => onDownloadTemplate('csv')}
              >
                CSV {t('knowledge.qaPairs.template')}
              </Button>
            </div>
          </div>
        </div>
      }
    />
  );
};

export type { QAPairUploadModalProps };
export default QAPairUploadModal;
