import React from 'react';
import { Skeleton } from 'antd';

export const OpspilotProviderGridSkeleton: React.FC = () => {
  return (
    <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 md:grid-cols-3 lg:grid-cols-4 2xl:grid-cols-5">
      {Array.from({ length: 8 }, (_, index) => (
        <div key={index} className="rounded-xl border border-(--color-border-1) bg-(--color-bg) p-4">
          <div className="flex items-start justify-between">
            <div style={{ flex: '0 0 auto' }}>
              <Skeleton.Avatar
                size={45}
                shape="square"
                active
                className="rounded-md"
              />
            </div>
            <div className="ml-2 flex-1">
              <Skeleton.Input
                size="small"
                active
                style={{ width: '80%', height: '16px', marginBottom: '8px' }}
              />
              <Skeleton.Input
                size="small"
                active
                style={{ width: '50%', height: '12px' }}
              />
            </div>
            <div className="cursor-pointer">
              <Skeleton.Avatar
                size={16}
                shape="circle"
                active
              />
            </div>
          </div>
        </div>
      ))}
    </div>
  );
};

export const OpspilotProviderModelTreeSkeleton: React.FC = () => {
  return (
    <div className="flex h-full flex-col rounded-md" style={{ backgroundColor: 'var(--color-bg-1)' }}>
      <div className="flex items-center justify-between gap-2 border-b p-3" style={{ borderColor: 'var(--color-border-2)' }}>
        <Skeleton.Input
          size="small"
          active
          style={{ width: '120px', height: '24px' }}
        />
        <Skeleton.Avatar
          size={24}
          shape="square"
          active
          className="rounded"
        />
      </div>

      <div className="flex-1 overflow-auto p-2">
        <div className="space-y-2">
          {Array.from({ length: 6 }, (_, index) => (
            <div key={index} className="flex items-center justify-between rounded p-2">
              <div className="flex flex-1 items-center">
                <Skeleton.Input
                  size="small"
                  active
                  style={{ width: '60%', height: '14px' }}
                />
              </div>
              <Skeleton.Input
                size="small"
                active
                style={{ width: '30px', height: '14px' }}
              />
            </div>
          ))}
        </div>
      </div>
    </div>
  );
};
