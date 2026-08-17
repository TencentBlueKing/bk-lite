import React from 'react';
import { Skeleton } from 'antd';

export const ProviderGridSkeleton: React.FC = () => {
  return (
    <div className="grid grid-cols-1 sm:grid-cols-2 md:grid-cols-3 lg:grid-cols-4 2xl:grid-cols-5 gap-4">
      {Array.from({ length: 8 }, (_, index) => (
        <div key={index} className="rounded-xl border border-(--color-border-1) bg-(--color-bg) p-4">
          <div className="flex justify-between items-start">
            <div className="shrink-0">
              <Skeleton.Avatar
                size={45}
                shape="square"
                active
                className="rounded-md"
              />
            </div>
            <div className="flex-1 ml-2">
              <Skeleton.Input
                size="small"
                active
                style={{ width: '80%', height: 16, marginBottom: 8 }}
              />
              <Skeleton.Input
                size="small"
                active
                style={{ width: '50%', height: 12 }}
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
