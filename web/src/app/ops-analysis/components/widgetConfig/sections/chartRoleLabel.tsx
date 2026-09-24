import React from 'react';
import { QuestionCircleOutlined, ReloadOutlined } from '@ant-design/icons';
import { Button, Tooltip } from 'antd';

export const ChartRoleLabel = ({
  text,
  tip,
}: {
  text: string;
  tip: string;
}) => (
  <span>
    {text}
    <Tooltip title={tip} styles={{ body: { maxWidth: 360 } }}>
      <QuestionCircleOutlined className="ml-1 cursor-help text-(--color-text-3)" />
    </Tooltip>
  </span>
);

export const RefreshFieldsButton = ({
  label,
  loading = false,
  disabled = false,
  onClick,
}: {
  label: string;
  loading?: boolean;
  disabled?: boolean;
  onClick?: () => void;
}) => (
  <Button
    type="text"
    size="small"
    icon={<ReloadOutlined aria-hidden />}
    onClick={onClick}
    loading={loading}
    disabled={disabled}
    className="h-6 px-1.5 text-xs text-(--color-text-3) hover:text-(--color-primary)"
  >
    {label}
  </Button>
);
