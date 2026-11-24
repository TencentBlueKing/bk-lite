'use client';

import { useCallback, useEffect, useRef, useState } from 'react';
import { Alert, Button, Spin } from 'antd';
import { ItsmBackButton } from './back-button';

export function useDesignerLoad<T>(enabled: boolean, read: () => Promise<T>, apply: (data: T) => void) {
  const [ready, setReady] = useState(false);
  const [error, setError] = useState('');
  const sequence = useRef(0);
  const load = useCallback(async () => {
    const request = ++sequence.current;
    setReady(false);
    setError('');
    try {
      const data = await read();
      if (request !== sequence.current) return;
      apply(data);
      setReady(true);
    } catch (cause) {
      if (request === sequence.current) setError(cause instanceof Error ? cause.message : '加载失败');
    }
  }, [read, apply]);

  useEffect(() => {
    if (enabled) void load();
    return () => { sequence.current++; };
  }, [enabled, load]);

  return { ready, error, load };
}

export function DesignerLoadStatus({ error, retry, href, label }: { error: string; retry: () => void; href: string; label: string }) {
  if (!error) return <Spin aria-label="正在加载设计" />;
  return <Alert type="error" message={error} action={<div className="flex gap-2">
    <ItsmBackButton href={href} label={label} /><Button onClick={retry}>重试</Button>
  </div>} />;
}
