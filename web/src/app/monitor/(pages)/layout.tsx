'use client';

import { Suspense } from 'react';
import { Spin } from 'antd';
import CommonProvider from '@/app/monitor/context/common';
import '@/app/monitor/styles/index.css';

export default function RootMonitor({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  // 不再等 useApiClient token 就绪才渲染子树,避免点「集成」白屏;
  // 各页面 effect 仍用 isLoading 自行等待发请求。
  // Suspense：覆盖 (pages) 下所有 useSearchParams 调用（含深层 dashboard/queryPanel），
  // 满足 Next 对 CSR bailout 的边界要求，避免日后 prerender 范围扩大时 build 突然失败。
  return (
    <CommonProvider>
      <Suspense
        fallback={
          <div className="w-full h-full flex items-center justify-center">
            <Spin size="large" />
          </div>
        }
      >
        {children}
      </Suspense>
    </CommonProvider>
  );
}
