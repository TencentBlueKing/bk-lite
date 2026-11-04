'use client';

import { useEffect, useState } from 'react';
import { Button, Toast } from 'antd-mobile';
import { useTranslation } from '@/utils/i18n';
import { loadOauthLoginBindings, startBrowserExternalLogin } from './browser';
import { externalSignInMessageId } from './external-sign-in-label';
import { LOGIN_ACTION_BUTTON_CLASS, loginActionButtonStyle } from './login-button-style';
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
    <div style={{ display: 'flex', flexDirection: 'column', paddingTop: 8 }}>
      <div
        style={{
          display: 'flex',
          alignItems: 'center',
          gap: 12,
          marginBottom: 12,
          fontSize: 14,
          color: '#9ca3af',
        }}
      >
        <span style={{ height: 1, flex: 1, backgroundColor: '#e5e7eb' }} />
        <span>{t('login.or')}</span>
        <span style={{ height: 1, flex: 1, backgroundColor: '#e5e7eb' }} />
      </div>
      {bindings.map((binding, index) => {
        const unavailable = disabled || startingId !== null;
        return (
          <div
            key={binding.id}
            style={{ marginBottom: index < bindings.length - 1 ? 12 : 0 }}
          >
            <Button
              loading={startingId === binding.id}
              disabled={unavailable}
              className={LOGIN_ACTION_BUTTON_CLASS}
              onClick={() => {
                void start(binding);
              }}
              style={{
                ...loginActionButtonStyle(unavailable),
                width: '100%',
                display: 'block',
              }}
            >
              {t(externalSignInMessageId(binding.name), undefined, { name: binding.name })}
            </Button>
          </div>
        );
      })}
    </div>
  );
}
