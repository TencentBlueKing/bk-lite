import React from 'react';
import { Tooltip, Upload } from 'antd';
import { SendOutlined } from '@ant-design/icons';

export const distributeEntryVisible = (enabled?: boolean) => enabled === true;

interface DistributeFileButtonProps {
  enabled?: boolean;
  disabled?: boolean;
  label: string;
  onFile: (file: File) => void;
}

const DistributeFileButton: React.FC<DistributeFileButtonProps> = ({
  enabled,
  disabled,
  label,
  onFile,
}) => {
  if (!distributeEntryVisible(enabled)) {
    return null;
  }
  return (
    <Upload
      fileList={[]}
      beforeUpload={(file) => {
        onFile(file);
        return Upload.LIST_IGNORE;
      }}
      showUploadList={false}
    >
      <Tooltip title={label}>
        <button
          type="button"
          disabled={disabled}
          className="flex h-7 w-7 items-center justify-center rounded-md text-[var(--color-text-3)] hover:bg-[var(--color-fill-2)] hover:text-[var(--color-text-1)] transition-colors disabled:opacity-40"
          aria-label={label}
        >
          <SendOutlined className="text-sm" />
        </button>
      </Tooltip>
    </Upload>
  );
};

export default DistributeFileButton;
