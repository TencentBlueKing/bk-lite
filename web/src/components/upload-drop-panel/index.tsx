'use client';

import React from 'react';
import { Upload } from 'antd';
import type { UploadProps } from 'antd';
import { InboxOutlined } from '@ant-design/icons';

const { Dragger } = Upload;

export interface UploadDropPanelProps {
  name?: string;
  fileList: UploadProps['fileList'];
  onChange?: UploadProps['onChange'];
  customRequest?: UploadProps['customRequest'];
  beforeUpload?: UploadProps['beforeUpload'];
  onRemove?: UploadProps['onRemove'];
  accept?: string;
  maxCount?: number;
  multiple?: boolean;
  directory?: boolean;
  showUploadList?: UploadProps['showUploadList'];
  icon?: React.ReactNode;
  uploadText: React.ReactNode;
  uploadHint?: React.ReactNode;
  className?: string;
  children?: React.ReactNode;
}

const UploadDropPanel: React.FC<UploadDropPanelProps> = ({
  name,
  fileList,
  onChange,
  customRequest,
  beforeUpload,
  onRemove,
  accept,
  maxCount,
  multiple,
  directory,
  showUploadList,
  icon = <InboxOutlined />,
  uploadText,
  uploadHint,
  className = 'w-full',
  children,
}) => {
  return (
    <div>
      <Dragger
        name={name}
        fileList={fileList}
        onChange={onChange}
        customRequest={customRequest}
        beforeUpload={beforeUpload}
        onRemove={onRemove}
        accept={accept}
        maxCount={maxCount}
        multiple={multiple}
        directory={directory}
        showUploadList={showUploadList}
        className={className}
      >
        <p className="ant-upload-drag-icon">{icon}</p>
        <p className="ant-upload-text">{uploadText}</p>
        {uploadHint ? <div className="ant-upload-hint">{uploadHint}</div> : null}
      </Dragger>
      {children}
    </div>
  );
};

export default UploadDropPanel;
