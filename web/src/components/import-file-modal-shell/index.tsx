import React from 'react';
import type { UploadProps } from 'antd';
import OperateFormModal from '@/components/operate-form-modal';
import SingleFileUploadPanel from '@/components/single-file-upload-panel';

interface ImportFileModalShellProps {
  title?: React.ReactNode;
  subTitle?: React.ReactNode;
  beforeUploadPanel?: React.ReactNode;
  visible?: boolean;
  open?: boolean;
  width?: number;
  confirmLoading?: boolean;
  confirmDisabled?: boolean;
  primaryFirst?: boolean;
  onConfirm: () => void;
  onCancel: () => void;
  confirmText: React.ReactNode;
  cancelText: React.ReactNode;
  footerExtra?: React.ReactNode;
  uploadProps: Pick<
    UploadProps,
    | 'customRequest'
    | 'onChange'
    | 'onRemove'
    | 'fileList'
    | 'accept'
    | 'showUploadList'
    | 'beforeUpload'
    | 'maxCount'
  > & {
    uploadText?: React.ReactNode;
    uploadHint?: React.ReactNode;
    icon?: React.ReactNode;
    children?: React.ReactNode;
  };
  afterUploadPanel?: React.ReactNode;
}

const ImportFileModalShell: React.FC<ImportFileModalShellProps> = ({
  title,
  subTitle,
  beforeUploadPanel,
  visible,
  open,
  width,
  confirmLoading = false,
  confirmDisabled = false,
  primaryFirst = true,
  onConfirm,
  onCancel,
  confirmText,
  cancelText,
  footerExtra,
  uploadProps,
  afterUploadPanel,
}) => {
  return (
    <OperateFormModal
      title={title}
      subTitle={subTitle}
      open={open}
      visible={visible}
      width={width}
      onCancel={onCancel}
      confirmText={confirmText}
      cancelText={cancelText}
      confirmLoading={confirmLoading}
      confirmDisabled={confirmDisabled}
      onConfirm={onConfirm}
      primaryFirst={primaryFirst}
      extra={footerExtra}
    >
      {beforeUploadPanel}
      <SingleFileUploadPanel
        customRequest={uploadProps.customRequest}
        onChange={uploadProps.onChange}
        onRemove={uploadProps.onRemove}
        fileList={uploadProps.fileList}
        accept={uploadProps.accept}
        showUploadList={uploadProps.showUploadList}
        beforeUpload={uploadProps.beforeUpload}
        maxCount={uploadProps.maxCount}
        uploadText={uploadProps.uploadText}
        uploadHint={uploadProps.uploadHint}
        icon={uploadProps.icon}
      >
        {uploadProps.children}
      </SingleFileUploadPanel>
      {afterUploadPanel}
    </OperateFormModal>
  );
};

export default ImportFileModalShell;
