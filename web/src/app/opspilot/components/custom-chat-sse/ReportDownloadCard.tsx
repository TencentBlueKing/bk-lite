'use client';

import React, { useCallback } from 'react';
import { Tag } from 'antd';
import { DownloadOutlined, FileWordOutlined } from '@ant-design/icons';
import { ReportFileDownload } from '@/app/opspilot/types/global';
import { normalizeSafeDownloadUrl } from './downloadUrl';

interface ReportDownloadCardProps {
  download: ReportFileDownload;
}

const ReportDownloadCard: React.FC<ReportDownloadCardProps> = ({ download }) => {
  const normalizedFileUrl = normalizeSafeDownloadUrl(download.file_url);

  const handleDownload = useCallback(() => {
    if (normalizedFileUrl) {
      const link = document.createElement('a');
      link.href = normalizedFileUrl;
      link.download = download.filename;
      document.body.appendChild(link);
      link.click();
      document.body.removeChild(link);
      return;
    }

    if (!download.content_base64) {
      return;
    }

    const byteCharacters = atob(download.content_base64);
    const byteNumbers = new Array(byteCharacters.length);
    for (let i = 0; i < byteCharacters.length; i++) {
      byteNumbers[i] = byteCharacters.charCodeAt(i);
    }
    const byteArray = new Uint8Array(byteNumbers);
    const blob = new Blob([byteArray], { type: download.mime_type });
    const url = URL.createObjectURL(blob);
    const link = document.createElement('a');
    link.href = url;
    link.download = download.filename;
    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);
    URL.revokeObjectURL(url);
  }, [download, normalizedFileUrl]);

  return (
    <Tag
      icon={<FileWordOutlined />}
      color="blue"
      className="mt-2 cursor-pointer !text-xs !py-0.5 !px-2"
      onClick={handleDownload}
    >
      {download.filename} <DownloadOutlined className="ml-1" />
    </Tag>
  );
};

export default ReportDownloadCard;
