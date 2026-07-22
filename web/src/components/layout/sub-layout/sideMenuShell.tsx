'use client';

import React from 'react';
import { ArrowLeftOutlined } from '@ant-design/icons';

interface SideMenuShellProps {
  children: React.ReactNode;
  intro?: React.ReactNode;
  showBackButton?: boolean;
  showProgress?: boolean;
  taskProgressComponent?: React.ReactNode;
  onBackButtonClick?: () => void;
  className?: string;
  introClassName?: string;
  navClassName?: string;
}

const SideMenuShell: React.FC<SideMenuShellProps> = ({
  children,
  intro,
  showBackButton = true,
  showProgress = false,
  taskProgressComponent,
  onBackButtonClick,
  className = '',
  introClassName = '',
  navClassName = '',
}) => {
  return (
    <aside className={`w-[216px] pr-4 flex flex-shrink-0 flex-col h-full ${className}`.trim()}>
      {intro && (
        <div className={`p-4 rounded-md mb-3 h-[80px] ${introClassName}`.trim()}>
          {intro}
        </div>
      )}
      <nav className={`flex-1 relative rounded-md ${navClassName}`.trim()}>
        {children}
        {showProgress && taskProgressComponent}
        {showBackButton && (
          <button
            className="absolute bottom-4 left-4 flex items-center py-2 rounded-md text-sm"
            onClick={onBackButtonClick}
          >
            <ArrowLeftOutlined className="mr-2" />
          </button>
        )}
      </nav>
    </aside>
  );
};

export default SideMenuShell;
