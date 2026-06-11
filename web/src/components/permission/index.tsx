import React from 'react';
import { Tooltip } from 'antd';
import usePermissions from '@/hooks/usePermissions';
import { useTranslation } from '@/utils/i18n';

interface PermissionWrapperProps {
  requiredPermissions: string[];
  instPermissions?: string[];
  fallback?: React.ReactNode;
  tooltip?: string;
  className?: string;
}

const PermissionWrapper: React.FC<React.PropsWithChildren<PermissionWrapperProps>> = ({
  requiredPermissions,
  instPermissions,
  fallback = null,
  tooltip,
  className,
  children
}) => {
  const { t } = useTranslation();
  const { hasPermission } = usePermissions();
  const instancePermissions = instPermissions || ['Operate'];

  if (hasPermission(requiredPermissions) && instancePermissions.includes('Operate')) {
    return <span className={className}>{children}</span>;
  }

  return (
    <Tooltip title={tooltip ?? t('common.noAuth')} zIndex={99999}>
      <div
        className={className}
        style={{ display: 'inline-block', cursor: 'not-allowed' }}
        onClick={(e) => e.stopPropagation()}
      >
        <span style={{ pointerEvents: 'none', opacity: 0.5 }}>
          {fallback || children}
        </span>
      </div>
    </Tooltip>
  );
};

export default React.memo(PermissionWrapper, (prevProps, nextProps) => {
  return (
    prevProps.requiredPermissions === nextProps.requiredPermissions &&
    prevProps.fallback === nextProps.fallback &&
    prevProps.tooltip === nextProps.tooltip &&
    prevProps.className === nextProps.className
  );
});
