import React from 'react';
import { Skeleton } from 'antd';

export const ProviderGridSkeleton: React.FC = () => {
  return (
    <div className="grid grid-cols-1 sm:grid-cols-2 md:grid-cols-3 lg:grid-cols-4 2xl:grid-cols-5 gap-4">
      {Array.from({ length: 8 }, (_, index) => (
        <div key={index} className="rounded-lg p-4 border border-gray-200">
          <div className="flex justify-between items-start">
            <div style={{flex: '0 0 auto'}}>
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

export const ModelTreeSkeleton: React.FC = () => {
  return (
    <div className="h-full flex flex-col bg-[var(--color-bg-1)] rounded-md">
      <div className="flex justify-between items-center p-3 border-b border-[var(--color-border-2)] gap-2">
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
      
      <div className="flex-1 p-2 overflow-auto">
        <div className="space-y-2">
          {Array.from({ length: 6 }, (_, index) => (
            <div key={index} className="flex items-center justify-between p-2 rounded">
              <div className="flex items-center flex-1">
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