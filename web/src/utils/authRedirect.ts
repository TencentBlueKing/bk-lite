export const AUTH_POPUP_SUCCESS_MESSAGE = 'bk-lite-auth-popup-success';

function isThirdLoginFlagEnabled(thirdLogin?: string | boolean | null): boolean {
  if (typeof thirdLogin === 'boolean') {
    return thirdLogin;
  }

  return thirdLogin === 'true' || thirdLogin === '1';
}

export function resolveThirdLoginFlag(...flags: Array<string | boolean | null | undefined>): string | undefined {
  const matchedFlag = flags.find((flag) => isThirdLoginFlagEnabled(flag));

  if (matchedFlag === undefined || matchedFlag === null) {
    return undefined;
  }

  return 'true';
}

function appendTokenToRelativeUrl(targetUrl: string, token: string): string {
  const hashIndex = targetUrl.indexOf('#');
  const pathWithSearch = hashIndex >= 0 ? targetUrl.slice(0, hashIndex) : targetUrl;
  const hash = hashIndex >= 0 ? targetUrl.slice(hashIndex) : '';
  const queryIndex = pathWithSearch.indexOf('?');
  const pathname = queryIndex >= 0 ? pathWithSearch.slice(0, queryIndex) : pathWithSearch;
  const search = queryIndex >= 0 ? pathWithSearch.slice(queryIndex + 1) : '';
  const searchParams = new URLSearchParams(search);

  searchParams.set('token', token);

  const nextSearch = searchParams.toString();

  return `${pathname}${nextSearch ? `?${nextSearch}` : ''}${hash}`;
}

function isSameOriginUrl(targetUrl: string, knownOrigin?: string): boolean {
  try {
    const parsed = new URL(targetUrl);
    // Prefer an explicitly supplied origin (e.g. derived from request headers in
    // server components) over window.location.origin so that this function works
    // correctly in both SSR and client-side contexts.
    const currentOrigin =
      knownOrigin ?? (typeof window !== 'undefined' ? window.location.origin : '');
    if (!currentOrigin) {
      // No origin available (SSR without explicit origin) — cannot validate, reject.
      return false;
    }
    return parsed.origin === currentOrigin;
  } catch {
    return false;
  }
}

export function buildThirdLoginCallbackUrl(
  callbackUrl?: string,
  token?: string,
  thirdLogin?: string | boolean | null,
  currentOrigin?: string,
): string {
  const targetUrl = callbackUrl || '/';

  if (!isThirdLoginFlagEnabled(thirdLogin) || !token) {
    return targetUrl;
  }

  try {
    // Protocol-relative URLs (e.g. "//attacker.com/...") start with "/" but
    // are interpreted by browsers as cross-origin. Detect and block them before
    // the relative-path branch.
    const isProtocolRelative = targetUrl.startsWith('//');
    const isRelativePath = targetUrl.startsWith('/') && !isProtocolRelative;

    if (isRelativePath) {
      return appendTokenToRelativeUrl(targetUrl, token);
    }

    // Reject absolute URLs (including protocol-relative) pointing to a
    // different origin to prevent open redirect attacks that could exfiltrate
    // the auth token to an attacker-controlled server.
    if (isProtocolRelative || !isSameOriginUrl(targetUrl, currentOrigin)) {
      console.warn(
        'buildThirdLoginCallbackUrl: cross-origin callbackUrl rejected, falling back to "/"',
        // Log only the origin portion to avoid echoing attacker-controlled path/query into logs.
        (() => { try { return new URL(targetUrl).origin; } catch { return '[invalid URL]'; } })(),
      );
      return '/';
    }

    const url = new URL(targetUrl);
    url.searchParams.set('token', token);
    return url.toString();
  } catch (error) {
    console.error('Failed to build third login callback URL:', error);
    return '/';
  }
}

export function buildOauthCallbackBridgeUrl(
  callbackUrl?: string,
  thirdLogin?: string | boolean | null,
  provider?: string | null,
): string {
  const targetUrl = callbackUrl || '/';

  if (!isThirdLoginFlagEnabled(thirdLogin)) {
    return targetUrl;
  }

  const searchParams = new URLSearchParams({
    callbackUrl: targetUrl,
    thirdLogin: 'true',
  });

  if (provider) {
    searchParams.set('provider', provider);
  }

  return `/auth/signin?${searchParams.toString()}`;
}

export function buildPopupSigninUrl(options?: {
  callbackUrl?: string;
  thirdLogin?: string | boolean | null;
  provider?: string | null;
}): string {
  const targetUrl = options?.callbackUrl || '/';
  const searchParams = new URLSearchParams({
    callbackUrl: targetUrl,
    popup: 'true',
  });

  if (isThirdLoginFlagEnabled(options?.thirdLogin)) {
    searchParams.set('thirdLogin', 'true');
  }

  if (options?.provider) {
    searchParams.set('provider', options.provider);
  }

  return `/auth/signin?${searchParams.toString()}`;
}

export function buildWechatPopupUrl(options?: {
  callbackUrl?: string;
  thirdLogin?: string | boolean | null;
}): string {
  const targetUrl = options?.callbackUrl || '/';
  const searchParams = new URLSearchParams({
    callbackUrl: targetUrl,
  });

  if (isThirdLoginFlagEnabled(options?.thirdLogin)) {
    searchParams.set('thirdLogin', 'true');
  }

  return `/auth/wechat-popup?${searchParams.toString()}`;
}
