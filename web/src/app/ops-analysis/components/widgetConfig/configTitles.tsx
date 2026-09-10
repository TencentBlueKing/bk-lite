import React from 'react';

export const ConfigSectionTitle: React.FC<{ children: React.ReactNode }> = ({
  children,
}) => (
  <h3 className="mb-4 text-sm font-semibold leading-6 text-(--color-text-1)">
    {children}
  </h3>
);

export const ConfigGroupTitle: React.FC<{
  children: React.ReactNode;
  extra?: React.ReactNode;
  actions?: React.ReactNode;
  className?: string;
}> = ({ children, extra, actions, className }) => (
  <div
    className={`mb-3 flex min-h-5 items-center justify-between gap-2${
      className ? ` ${className}` : ''
    }`}
  >
    <h4 className="m-0 flex min-w-0 items-center gap-1.5 text-[13px] font-semibold leading-5 text-(--color-text-2)">
      <span
        className="h-3 w-0.5 shrink-0 rounded-full bg-(--color-primary)"
        aria-hidden
      />
      <span className="min-w-0">{children}</span>
      {extra}
    </h4>
    {actions}
  </div>
);
