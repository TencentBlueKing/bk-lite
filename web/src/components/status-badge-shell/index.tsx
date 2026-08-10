import type { CSSProperties, ReactNode } from 'react';
import SemanticBadge from '@/components/semantic-badge';

export interface StatusBadgePalette {
  textColor: string;
  backgroundColor: string;
}

export interface StatusBadgeShellProps {
  label: ReactNode;
  palette: StatusBadgePalette;
  className?: string;
  minWidth?: CSSProperties['minWidth'];
  centered?: boolean;
}

const StatusBadgeShell = ({
  label,
  palette,
  className = '',
  minWidth,
  centered = false,
}: StatusBadgeShellProps) => {
  return (
    <span className={className}>
      <SemanticBadge
        label={label}
        textColor={palette.textColor}
        backgroundColor={palette.backgroundColor}
        minWidth={minWidth}
        centered={centered}
      />
    </span>
  );
};

export default StatusBadgeShell;
