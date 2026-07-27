import type { CSSProperties, ReactNode } from 'react';

interface SemanticBadgeProps {
  label: ReactNode;
  textColor: string;
  backgroundColor: string;
  minWidth?: CSSProperties['minWidth'];
  centered?: boolean;
}

const SemanticBadge = ({
  label,
  textColor,
  backgroundColor,
  minWidth,
  centered = false,
}: SemanticBadgeProps) => {
  const className = centered
    ? 'inline-flex items-center justify-center rounded px-2 py-0.5 text-xs font-medium'
    : 'inline-flex items-center rounded px-2 py-0.5 text-xs font-medium';

  return (
    <span
      className={className}
      style={{ color: textColor, backgroundColor, minWidth }}
    >
      {label}
    </span>
  );
};

export default SemanticBadge;
