'use client';

import { useEffect } from 'react';
import { useRouter } from 'next/navigation';
import { SpinLoading } from 'antd-mobile';

export default function Home() {
  const router = useRouter();

  useEffect(() => {
    router.replace('/conversations');
  }, [router]);

  return (
    <div className="flex flex-col items-center justify-center h-full gap-3">
      <SpinLoading color="primary" style={{ '--size': '32px' }} />
    </div>
  );
}
