'use client';

import { useEffect, useState } from 'react';
import { Button, Spin } from 'antd';
import { signIn, useSession } from 'next-auth/react';
import { useParams, useRouter } from 'next/navigation';
import { useDashboardShareApi } from '@/app/ops-analysis/api/dashboardShare';

export default function DashboardShareTokenPage() {
  const params = useParams<{ token: string }>();
  const router = useRouter();
  const { status } = useSession();
  const { exchangeShare } = useDashboardShareApi();
  const [invalid, setInvalid] = useState(false);

  useEffect(() => {
    if (status === 'unauthenticated') {
      void signIn(undefined, { callbackUrl: window.location.href });
      return;
    }
    if (status !== 'authenticated' || !params.token) return;
    let active = true;
    exchangeShare(params.token)
      .then((result) => {
        if (active) {
          router.replace(`/ops-analysis/share/session/${result.session_id}`);
        }
      })
      .catch(() => {
        if (active) setInvalid(true);
      });
    return () => {
      active = false;
    };
  }, [exchangeShare, params.token, router, status]);

  if (invalid) {
    return (
      <div className="fixed inset-0 z-50 flex items-center justify-center bg-[var(--color-bg-1)] p-8">
        <div className="w-full max-w-[400px] text-center">
          <h2 className="mb-2 text-base font-medium text-[var(--color-text-1)]">
            分享链接无效或已失效
          </h2>
          <p className="mb-6 text-sm leading-relaxed text-[var(--color-text-3)]">
            链接可能已被撤销、过期,或你没有访问权限。
          </p>
          <Button type="primary" onClick={() => router.push('/')}>
            返回首页
          </Button>
        </div>
      </div>
    );
  }
  return <Spin fullscreen tip="正在打开分享仪表盘" />;
}

