import React from 'react';

interface PanelShellProps {
  header?: React.ReactNode;
  footer?: React.ReactNode;
  children: React.ReactNode;
  className?: string;
  bodyClassName?: string;
  headerClassName?: string;
  footerClassName?: string;
}

const PanelShell: React.FC<PanelShellProps> = ({
  header,
  footer,
  children,
  className = '',
  bodyClassName = '',
  headerClassName = '',
  footerClassName = '',
}) => {
  return (
    <div className={`flex flex-col overflow-hidden ${className}`}>
      {header ? <div className={headerClassName}>{header}</div> : null}
      <div className={`flex-1 overflow-y-auto ${bodyClassName}`}>{children}</div>
      {footer ? <div className={footerClassName}>{footer}</div> : null}
    </div>
  );
};

export default PanelShell;
