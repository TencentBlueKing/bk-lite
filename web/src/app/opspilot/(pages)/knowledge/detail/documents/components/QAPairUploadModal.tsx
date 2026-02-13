'use client';

import React from 'react';
import { Button, Upload } from 'antd';
import type { UploadFile } from 'antd';
import { InboxOutlined } from '@ant-design/icons';
import OperateModal from '@/components/operate-modal';

const { Dragger } = Upload;

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
    <OperateModal
      title={t('common.import')}
      centered
      visible={visible}
      confirmLoading={confirmLoading}
      onOk={onOk}
      onCancel={onCancel}
      okButtonProps={{
        disabled: uploadingFiles.size > 0 || uploadedFiles.length === 0
      }}
    >
      <div>
        <Dragger
          accept="application/json,.csv"
          beforeUpload={onFileUpload}
          onRemove={handleRemove}
          fileList={fileList}
        >
          <p className="ant-upload-drag-icon">
            <InboxOutlined />
          </p>
          <p className="ant-upload-text">{t('knowledge.qaPairs.dragOrClick')}</p>
          <p className="ant-upload-hint text-xs">{t('knowledge.qaPairs.uploadHint')}</p>
        </Dragger>
        
        <div className="pt-4">
          <div className="flex items-center text-xs">
            <span className="text-gray-600">{t('knowledge.qaPairs.downloadTemplate')}：</span>
            <div className="flex gap-2">
              <Button 
                type="link" 
                size="small"
                className='text-xs'
                onClick={() => onDownloadTemplate('json')}
              >
                JSON {t('knowledge.qaPairs.template')}
              </Button>
              <Button 
                type="link" 
                size="small"
                className='text-xs'
                onClick={() => onDownloadTemplate('csv')}
              >
                CSV {t('knowledge.qaPairs.template')}
              </Button>
            </div>
          </div>
        </div>
      </div>
    </OperateModal>
  );
};

export default QAPairUploadModal;
