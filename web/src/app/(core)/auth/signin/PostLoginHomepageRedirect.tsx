'use client';

import React, { useEffect } from 'react';
import { isScreenModeEnabled, withScreenQuery } from '@/console-layout';
import { resolvePostLoginHref } from '@/app/ops-analysis/utils/homepageLanding';

interface PostLoginHomepageRedirectProps {
  targetUrl: string;
  token?: string;
}

/** 已登录且目标是裸工作台时，按首页配置补上 dashboard_id，再离开登录页。 */
const PostLoginHomepageRedirect: React.FC<PostLoginHomepageRedirectProps> = ({
  targetUrl,
  token,
}) => {
  useEffect(() => {
    let cancelled = false;
    void (async () => {
      const landed = await resolvePostLoginHref(targetUrl, token, window.location.origin);
      if (cancelled) {
        return;
      }
      const nextUrl = withScreenQuery(
        landed,
        isScreenModeEnabled(window.location.search),
        window.location.origin,
      );
      window.location.replace(nextUrl);
    })();
    return () => {
      cancelled = true;
    };
  }, [targetUrl, token]);

  return null;
};

export default PostLoginHomepageRedirect;
