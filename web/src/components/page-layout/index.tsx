import React from 'react';

interface CustomLayoutProps {
  topSection?: React.ReactNode;
  leftSection?: React.ReactNode;
  rightSection: React.ReactNode;
  height?: string;
}

const CustomLayout: React.FC<CustomLayoutProps> = ({ topSection, leftSection, rightSection, height }) => {
  return (
    <div className="w-full">
      {topSection && <div>{topSection}</div>}

      <div
        className={`flex w-full min-w-0 overflow-hidden ${topSection ? 'mt-4' : ''}`}
        style={{
          height: height || (topSection ? 'calc(100vh - 185px)' : 'calc(100vh - 105px)'),
        }}
      >
        {leftSection && (
          <div
            className="p-4 w-[230px] flex-shrink-0 flex flex-col justify-items-center items-center rounded-md mr-[17px] bg-[var(--color-bg)]"
          >
            {leftSection}
          </div>
        )}
        <div
          className="min-w-0 flex-1 h-full rounded-md overflow-x-auto overflow-y-hidden p-4 bg-[var(--color-bg)]"
        >
          {rightSection}
        </div>
      </div>
    </div>
  );
};

export default CustomLayout;
