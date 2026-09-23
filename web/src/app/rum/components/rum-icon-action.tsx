'use client';

import type { MouseEvent } from 'react';
import { Button } from 'antd';

/** RUM 表格行内操作：纯中文文案 + AntD `link` `small`，不加图标。 */
export default function RumIconAction({
  title,
  onClick,
  danger,
  disabled,
  loading,
  className,
}: {
  title: string;
  onClick?: (event: MouseEvent<HTMLElement>) => void;
  danger?: boolean;
  disabled?: boolean;
  loading?: boolean;
  className?: string;
}) {
  return (
    <Button
      type="link"
      size="small"
      onClick={onClick}
      danger={danger}
      disabled={disabled}
      loading={loading}
      aria-label={title}
      className={['!px-0 hover:!underline', className].filter(Boolean).join(' ')}
    >
      {title}
    </Button>
  );
}
