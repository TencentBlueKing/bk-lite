'use client';

import CommonProvider from '@/app/monitor/context/common';
import '@/app/monitor/styles/index.css';

export default function RootMonitor({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  // 不再等 useApiClient token 就绪才渲染子树,避免点「集成」白屏;
  // 各页面 effect 仍用 isLoading 自行等待发请求。
  return <CommonProvider>{children}</CommonProvider>;
}
