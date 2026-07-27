'use client';

import React from 'react';
import type { UploadProps } from 'antd';
import { UploadOutlined } from '@ant-design/icons';
import UploadDropPanel, {
  type UploadDropPanelProps,
} from '@/components/upload-drop-panel';

interface MultiFileUploadPanelProps {
  name?: string;
  fileList: UploadProps['fileList'];
  onChange?: UploadProps['onChange'];
  customRequest?: UploadProps['customRequest'];
  beforeUpload?: UploadProps['beforeUpload'];
  onRemove?: UploadProps['onRemove'];
  accept?: string;
  multiple?: boolean;
  showUploadList?: UploadProps['showUploadList'];
  icon?: React.ReactNode;
  uploadText: React.ReactNode;
  uploadHint?: React.ReactNode;
  className?: string;
  children?: React.ReactNode;
}

const MultiFileUploadPanel: React.FC<MultiFileUploadPanelProps> = ({
  name = 'file',
  fileList,
  onChange,
  customRequest,
  beforeUpload,
  onRemove,
  accept,
  multiple = true,
  showUploadList,
  icon = <UploadOutlined />,
  uploadText,
  uploadHint,
  className = 'w-full',
  children,
}) => {
  const panelProps: UploadDropPanelProps = {
    name,
    fileList,
    onChange,
    customRequest,
    beforeUpload,
    onRemove,
    accept,
    multiple,
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

export default MultiFileUploadPanel;
