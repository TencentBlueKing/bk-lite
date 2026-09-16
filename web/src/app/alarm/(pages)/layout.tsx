'use client';

import React from 'react';
import CommonProvider from '@/app/alarm/context/common';
import { AliveScope } from 'react-activation';

export default function Layout({ children }: { children: React.ReactNode }) {
  return (
    <CommonProvider>
      <AliveScope>
        <div className="flex h-full min-h-0 w-full flex-1 flex-col">
          {children}
        </div>
      </AliveScope>
    </CommonProvider>
  );
}
