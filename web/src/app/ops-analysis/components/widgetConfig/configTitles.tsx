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

export const StyleSectionTabIcon: React.FC = () => (
  <svg viewBox="0 0 16 16" className={tabIconClass} fill="none" focusable="false">
    <path d="M2.75 4.25h10.5" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" />
    <path d="M2.75 8h10.5" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" />
    <path d="M2.75 11.75h10.5" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" />
    <circle cx="6" cy="4.25" r="1.35" fill="var(--color-bg)" stroke="currentColor" strokeWidth="1.5" />
    <circle cx="10.25" cy="8" r="1.35" fill="var(--color-bg)" stroke="currentColor" strokeWidth="1.5" />
    <circle cx="7.25" cy="11.75" r="1.35" fill="var(--color-bg)" stroke="currentColor" strokeWidth="1.5" />
  </svg>
);

export const ConfigSectionTitle: React.FC<{
  children: React.ReactNode;
  extra?: React.ReactNode;
  actions?: React.ReactNode;
}> = ({ children, extra, actions }) => {
  if (!extra && !actions) {
    return (
      <h3 className="mb-4 text-sm font-semibold leading-6 text-(--color-text-1)">
        {children}
      </h3>
    );
  }
  return (
    <div className="mb-4 flex items-center justify-between gap-2">
      <h3 className="m-0 flex min-w-0 items-center gap-1.5 text-sm font-semibold leading-6 text-(--color-text-1)">
        <span className="min-w-0">{children}</span>
        {extra}
      </h3>
      {actions}
    </div>
  );
};
