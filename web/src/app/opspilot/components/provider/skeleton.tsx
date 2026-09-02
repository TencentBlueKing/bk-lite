import React from 'react';
import { Skeleton } from 'antd';
import OpsPilotCardGridSkeleton from '@/app/opspilot/components/opspilot-card-grid-skeleton';

export const ProviderGridSkeleton: React.FC = () => {
  return <OpsPilotCardGridSkeleton />;
};

export const ModelTreeSkeleton: React.FC = () => {
  return (
    <div className="flex h-full flex-col rounded-md bg-[var(--color-bg-1)]">
      <div className="flex items-center justify-between gap-2 border-b border-[var(--color-border-2)] p-3">
        <Skeleton.Input
          size="small"
          active
          style={{ width: 120, height: 24 }}
        />
        <Skeleton.Avatar
          size={24}
          shape="square"
          active
          className="rounded"
        />
      </div>

      <div className="flex-1 p-2 overflow-auto">
        <div className="space-y-2">
          {Array.from({ length: 6 }, (_, index) => (
            <div key={index} className="flex items-center justify-between p-2 rounded">
              <div className="flex items-center flex-1">
                <Skeleton.Input
                  size="small"
                  active
                  style={{ width: '60%', height: 14 }}
                />
              </div>
              <Skeleton.Input
                size="small"
                active
                style={{ width: 30, height: 14 }}
              />
            </div>
          ))}
        </div>
      </div>
    </div>
  );
};
