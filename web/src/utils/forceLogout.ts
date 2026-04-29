import { signOut } from 'next-auth/react';
import { clearAuthToken } from '@/utils/crossDomainAuth';
import { isAuthPath, resetSessionExpiredState } from '@/utils/sessionExpiry';

let forceLogoutInProgress = false;

const buildLoginUrl = () => {
  if (typeof window === 'undefined') {
    return '/auth/signin';
  }

  const callbackUrl = isAuthPath(window.location.pathname) ? '/' : window.location.href;
  return `/auth/signin?callbackUrl=${encodeURIComponent(callbackUrl)}`;
};

export const forceLogoutAndRedirect = async () => {
  if (typeof window === 'undefined' || forceLogoutInProgress) {
    return;
  }

  forceLogoutInProgress = true;

  try {
    resetSessionExpiredState();

    // Best-effort: call federated-logout to revoke backend token
    try {
      await fetch('/api/auth/federated-logout', { method: 'POST' });
    } catch {
      // Non-blocking: proceed with logout even if revocation fails
    }

    clearAuthToken();
    await signOut({ redirect: false });
  } catch (error) {
    console.error('Force logout failed:', error);
  } finally {
    forceLogoutInProgress = false;
    window.location.replace(buildLoginUrl());
  }
};
