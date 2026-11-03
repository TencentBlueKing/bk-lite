'use client';

import { useEffect, useState } from 'react';
import { Button, Toast } from 'antd-mobile';
import { useTranslation } from '@/utils/i18n';
import { loadOauthLoginBindings, startBrowserExternalLogin } from './browser';
import type { PublicLoginBinding } from './types';

export function ExternalLoginButtons({ disabled }: { disabled: boolean }) {
  const { t } = useTranslation();
  const [bindings, setBindings] = useState<PublicLoginBinding[]>([]);
  const [startingId, setStartingId] = useState<number | null>(null);

  useEffect(() => {
    let active = true;
    loadOauthLoginBindings()
      .then((items) => {
        if (active) setBindings(items);
      })
      .catch(() => {
        if (active) setBindings([]);
      });
    return () => {
      active = false;
    };
  }, []);

  if (bindings.length === 0) return null;

  const start = async (binding: PublicLoginBinding) => {
    setStartingId(binding.id);
    try {
      const started = await startBrowserExternalLogin(binding);
      if (!started) {
        Toast.show({
          content: t('login.externalUnavailable', undefined, { name: binding.name }),
          icon: 'fail',
        });
      }
    } catch {
      Toast.show({
        content: t('login.externalUnavailable', undefined, { name: binding.name }),
        icon: 'fail',
      });
    } finally {
      setStartingId(null);
    }
  };

  return (
    <div className="space-y-3 pt-2">
      <div className="flex items-center gap-3 text-sm text-gray-400">
        <span className="h-px flex-1 bg-gray-200" />
        <span>{t('login.or')}</span>
        <span className="h-px flex-1 bg-gray-200" />
      </div>
      {bindings.map((binding) => (
        <Button
          key={binding.id}
          fill="outline"
          loading={startingId === binding.id}
          disabled={disabled || startingId !== null}
          className="w-full h-11"
          onClick={() => {
            void start(binding);
          }}
          style={{ fontSize: '16px' }}
        >
          {t('login.externalSignIn', undefined, { name: binding.name })}
        </Button>
      ))}
    </div>
  );
}
