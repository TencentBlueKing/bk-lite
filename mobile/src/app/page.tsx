'use client';

import { useEffect } from 'react';
import { useRouter } from 'next/navigation';
import { SpinLoading } from 'antd-mobile';
import { initSecureStorage, getToken } from '@/utils/secureStorage';

export default function Home() {
  const router = useRouter();

  useEffect(() => {
    const checkAuth = async () => {
      try {
        // 初始化安全存储
        await initSecureStorage();

        // 从安全存储获取 token
        const token = await getToken();

        if (token) {
          // 已登录，跳转到会话页
          router.replace('/conversation?id=1');
        } else {
          // 未登录，跳转到登录页
          router.replace('/login');
        }
      } catch (error) {
        console.error('Auth check failed:', error);
        router.replace('/login');
      }
    };

    checkAuth();
  }, [router]);

  return (
    <div className="flex flex-col items-center justify-center h-full gap-3">
      <SpinLoading color="primary" style={{ '--size': '32px' }} />
    </div>
  );
}
