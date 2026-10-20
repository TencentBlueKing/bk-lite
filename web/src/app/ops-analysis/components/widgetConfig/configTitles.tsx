import React from 'react';
import { LinkOutlined } from '@ant-design/icons';

const tabIconClass = 'size-4 shrink-0';

export const ConfigSectionTabLabel: React.FC<{
  icon: React.ReactNode;
  children: React.ReactNode;
}> = ({ icon, children }) => (
  <span className="inline-flex items-center gap-1.5 font-medium">
    <span className="inline-flex leading-none" aria-hidden>
      {icon}
    </span>
    {children}
  </span>
);

export const DataSectionTabIcon: React.FC = () => (
  <svg viewBox="0 0 16 16" className={tabIconClass} fill="none" focusable="false">
    <ellipse cx="8" cy="3.25" rx="5.15" ry="1.7" stroke="currentColor" strokeWidth="1.5" />
    <path
      d="M2.85 3.25v9.5c0 .94 2.3 1.7 5.15 1.7s5.15-.76 5.15-1.7v-9.5"
      stroke="currentColor"
      strokeWidth="1.5"
    />
    <path
      d="M2.85 8c0 .94 2.3 1.7 5.15 1.7s5.15-.76 5.15-1.7"
      stroke="currentColor"
      strokeWidth="1.5"
    />
  </svg>
);

export const InteractionSectionTabIcon: React.FC = () => (
  <LinkOutlined className="text-base" />
);

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
