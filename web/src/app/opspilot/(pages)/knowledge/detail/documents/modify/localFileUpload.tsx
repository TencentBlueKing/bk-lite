'use client';

import React, { useState, useEffect, useRef } from 'react';
import { Upload, message } from 'antd';
import { UploadOutlined } from '@ant-design/icons';
import { useTranslation } from '@/utils/i18n';
import { uploadChunks } from '@/app/opspilot/utils/upload';

const { Dragger } = Upload;

interface LocalFileUploadProps {
  onFileChange: (files: File[]) => void;
  initialFileList: any[];
}

const LocalFileUpload: React.FC<LocalFileUploadProps> = ({ onFileChange, initialFileList }) => {
  const { t } = useTranslation();
  const [fileList, setFileList] = useState<any[]>(initialFileList || []);
  const prevFileListRef = useRef<File[]>([]);

  useEffect(() => {
    const files = fileList.map(file => file.originFileObj).filter(Boolean) as File[];
    const prevFiles = prevFileListRef.current;

    // Compare current files with previous files
    const hasChanged =
      files.length !== prevFiles.length ||
      files.some((file, index) => file !== prevFiles[index]);

    if (hasChanged) {
      onFileChange(files);
      prevFileListRef.current = files; // Update the reference to the current file list
    }
  }, [fileList, onFileChange]);

  const handleBeforeUpload = (file: File) => {
    const allowedTypes = [
      'application/vnd.openxmlformats-officedocument.wordprocessingml.document', // .docx
      'application/pdf', // .pdf
      'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet', // .xlsx
      'text/plain', // .txt
      'text/markdown',  // .md (standard)
      'text/x-markdown', // .md (non-standard)
      'text/csv' // .csv
    ];
    const allowedExtensions = ['.docx', '.pdf', '.xlsx', '.txt', '.csv', '.md'];
    const isAllowedType = allowedTypes.includes(file.type);
    const isAllowedExtension = allowedExtensions.some(ext => file.name.endsWith(ext));
    if (!isAllowedType && !isAllowedExtension) {
      message.error(`${file.name} ${t('common.fileType')}`);
      return Upload.LIST_IGNORE;
    }
    return isAllowedType;
  };

  const handleCustomRequest = async (options: any) => {
    const { file, onSuccess, onError, onProgress } = options;
    try {
      await uploadChunks(file, (progressEvent) => {
        onProgress({
          percent: (progressEvent.loaded / progressEvent.total) * 100,
        });
      });
      onSuccess("ok");
    } catch (err) {
      onError(err);
    }
  };

  return (
    <div>
      <Dragger
        name="file"
        multiple
        fileList={fileList}
        beforeUpload={handleBeforeUpload}
        customRequest={handleCustomRequest}
        onChange={(info) => {
          setFileList(info.fileList);
        }}
      >
        <p className="ant-upload-drag-icon">
          <UploadOutlined />
        </p>
        <p className="ant-upload-text">{t('common.uploadText')}</p>
        <p className="ant-upload-hint">
          {t('common.supports')}: .docx .pdf .xlsx .txt .csv, .md...
        </p>
      </Dragger>
    </div>
  );
};

export default LocalFileUpload;
