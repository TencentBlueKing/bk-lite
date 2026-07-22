import React from 'react';
import { Spin } from 'antd';

export interface ChartRendererShellProps {
  loading?: boolean;
  error?: React.ReactNode;
  children?: React.ReactNode;
  containerClassName?: string;
  loadingClassName?: string;
  loadingContent?: React.ReactNode;
}

const ChartRendererShell: React.FC<ChartRendererShellProps> = ({
  loading = false,
  error = null,
  children,
  containerClassName = 'h-full',
  loadingClassName = 'flex h-full items-center justify-center',
  loadingContent,
}) => {
  return (
    <div className={containerClassName}>
      {loading ? (
        <div className={loadingClassName}>
          {loadingContent || <Spin size="small" />}
        </div>
      ) : error ? (
        error
      ) : (
        children
      )}
    </div>
  );
};

export default ChartRendererShell;
