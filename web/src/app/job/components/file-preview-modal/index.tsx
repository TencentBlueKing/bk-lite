import React from 'react';
import { Alert, Spin } from 'antd';
import OperateFormModal from '@/components/operate-form-modal';
import type { PlaybookFilePreview } from '@/app/job/types';

export interface JobFilePreviewModalProps {
  open: boolean;
  loading?: boolean;
  error?: string | null;
  preview: PlaybookFilePreview | null;
  previewLabel: string;
  loadingLabel: string;
  failedMessage: string;
  onCancel: () => void;
}

const JobFilePreviewModal: React.FC<JobFilePreviewModalProps> = ({
  open,
  loading = false,
  error,
  preview,
  previewLabel,
  loadingLabel,
  failedMessage,
  onCancel,
}) => {
  return (
    <OperateFormModal
      title={preview ? `${previewLabel}: ${preview.file_name}` : previewLabel}
      open={open}
      onCancel={onCancel}
      hideFooter
      width={800}
      styles={{ body: { maxHeight: '70vh', overflow: 'auto' } }}
    >
      {loading ? (
        <div className="flex items-center justify-center py-12">
          <Spin tip={loadingLabel} />
        </div>
      ) : error ? (
        <Alert
          message={failedMessage}
          description={error}
          type="error"
          showIcon
        />
      ) : preview ? (
        <div>
          <div className="mb-2 text-xs" style={{ color: 'var(--color-text-3)' }}>
            {preview.file_path} ({preview.file_size} bytes)
          </div>
          <pre
            className="overflow-auto rounded p-4 text-sm"
            style={{
              backgroundColor: 'var(--color-bg-1)',
              border: '1px solid var(--color-border)',
              maxHeight: '60vh',
              whiteSpace: 'pre-wrap',
              wordBreak: 'break-word',
            }}
          >
            <code>{preview.content}</code>
          </pre>
        </div>
      ) : null}
    </OperateFormModal>
  );
};

export default JobFilePreviewModal;
