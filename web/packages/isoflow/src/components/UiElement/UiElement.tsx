import React from 'react';
import { Card, SxProps } from '@mui/material';

interface Props {
  children: React.ReactNode;
  sx?: SxProps;
  style?: React.CSSProperties;
}

export const UiElement = ({ children, sx, style }: Props) => {
  return (
    <Card
      sx={{
        borderRadius: '8px',
        boxShadow: '0 8px 24px rgba(15, 23, 42, 0.08)',
        border: '1px solid var(--color-border-1)',
        bgcolor: 'var(--color-bg)',
        color: 'var(--color-text-1)',
        ...sx
      }}
      style={style}
    >
      {children}
    </Card>
  );
};
