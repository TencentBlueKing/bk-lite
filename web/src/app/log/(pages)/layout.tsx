'use client';

import CommonProvider from '@/app/log/context/common';
import '@/app/log/styles/index.css';

export default function RootLog({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  // 不再等 useApiClient token 就绪才渲染子树，避免侧栏切换时白屏闪一下；
  // 各页面 effect 仍用 isLoading 自行等待发请求。
  return <CommonProvider>{children}</CommonProvider>;
}
