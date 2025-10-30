'use client';

import { useEffect } from 'react';
import { useRouter } from 'next/navigation';
import { SpinLoading } from 'antd-mobile';

export default function Home() {
  const router = useRouter();

  useEffect(() => {
    // 检查是否已登录
    const token = typeof window !== 'undefined' ? localStorage.getItem('token') : null;

    if (token) {
      // 已登录，跳转到会话页
      router.replace('/conversation?id=1');
    } else {
      // 未登录，跳转到登录页
      router.replace('/login');
    }
  }, [router]);

  return (
    <div className="flex flex-col items-center justify-center h-full gap-3">
      <SpinLoading color="primary" style={{ '--size': '32px' }} />
    </div>
  );
}
