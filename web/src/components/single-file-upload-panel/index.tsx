'use client';

import React from 'react';
import { InboxOutlined } from '@ant-design/icons';
import type { UploadProps } from 'antd';
import UploadDropPanel, {
  type UploadDropPanelProps,
} from '@/components/upload-drop-panel';

interface SingleFileUploadPanelProps {
  fileList: UploadProps['fileList'];
  onChange?: UploadProps['onChange'];
  customRequest?: UploadProps['customRequest'];
  beforeUpload?: UploadProps['beforeUpload'];
  onRemove?: UploadProps['onRemove'];
  accept?: string;
  maxCount?: number;
  showUploadList?: UploadProps['showUploadList'];
  icon?: React.ReactNode;
  uploadText: React.ReactNode;
  uploadHint?: React.ReactNode;
  className?: string;
  children?: React.ReactNode;
}

const SingleFileUploadPanel: React.FC<SingleFileUploadPanelProps> = ({
  fileList,
  onChange,
  customRequest,
  beforeUpload,
  onRemove,
  accept,
  maxCount = 1,
  showUploadList,
  icon = <InboxOutlined />,
  uploadText,
  uploadHint,
  className = 'w-full',
  children,
}) => {
  const panelProps: UploadDropPanelProps = {
    fileList,
    onChange,
    customRequest,
    beforeUpload,
    onRemove,
    accept,
    maxCount,
    showUploadList,
    icon,
    uploadText,
    uploadHint,
    className,
    children,
  };

  return (
    <UploadDropPanel {...panelProps} />
  );
};

export default SingleFileUploadPanel;
