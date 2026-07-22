import type { ReactNode } from 'react';
import { Tooltip } from 'antd';

export interface LogMessagePreviewProps {
  value?: string | null;
  previewLength?: number;
  monospace?: boolean;
  tooltipMaxWidth?: string;
  children?: ReactNode;
}

const LogMessagePreview = ({
  value,
  previewLength = 80,
  monospace = true,
  tooltipMaxWidth = '500px',
  children,
}: LogMessagePreviewProps) => {
  if (!value) {
    return <>--</>;
  }

  const preview = value.length > previewLength ? `${value.slice(0, previewLength)}…` : value;
  const trigger = children || (
    <span
      className={`cursor-pointer text-xs text-[var(--color-text-1)] ${
        monospace ? 'font-mono' : ''
      }`}
    >
      {preview}
    </span>
  );

  return (
    <Tooltip
      title={
        <pre
          className="max-h-[300px] overflow-auto whitespace-pre-wrap text-xs"
          style={{ maxWidth: tooltipMaxWidth }}
        >
          {value}
        </pre>
      }
      placement="topLeft"
    >
      {trigger}
    </Tooltip>
  );
};

export default LogMessagePreview;
