import { createElement, type ReactNode } from 'react';

export const NETWORK_WHITELIST_REQUIRED = 'NETWORK_WHITELIST_REQUIRED';
export const NETWORK_WHITELIST_URL = '/system-manager/settings/network-whitelist';

interface RequestErrorPayload {
  code?: string;
  message?: string;
  data?: {
    network_whitelist_url?: string;
    action_label?: string;
  };
}

export interface RequestErrorPresentation {
  message: string;
  actionLabel: string;
  href: string;
  target: '_blank';
  rel: 'noopener noreferrer';
}

export const getRequestErrorPresentation = (
  payload: RequestErrorPayload | undefined,
): RequestErrorPresentation | null => {
  if (payload?.code !== NETWORK_WHITELIST_REQUIRED) return null;

  const href = payload.data?.network_whitelist_url;
  if (href !== NETWORK_WHITELIST_URL) return null;

  return {
    message: payload.message || '目标 IP 不在白名单内，请前往系统管理的白名单管理中添加。',
    actionLabel: payload.data?.action_label || '前往白名单管理',
    href,
    target: '_blank',
    rel: 'noopener noreferrer',
  };
};

export const renderRequestErrorPresentation = (
  presentation: RequestErrorPresentation,
): ReactNode => createElement(
  'span',
  null,
  presentation.message,
  ' ',
  createElement(
    'a',
    {
      href: presentation.href,
      target: presentation.target,
      rel: presentation.rel,
    },
    presentation.actionLabel,
  ),
);
