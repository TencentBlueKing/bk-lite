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

export function buildThirdLoginCallbackUrl(
  callbackUrl?: string,
  token?: string,
  thirdLogin?: string | boolean | null,
): string {
  const targetUrl = callbackUrl || '/';

  if (!isThirdLoginFlagEnabled(thirdLogin) || !token) {
    return targetUrl;
  }

  try {
    const isRelativePath = targetUrl.startsWith('/');

    if (isRelativePath) {
      return appendTokenToRelativeUrl(targetUrl, token);
    }

    const url = new URL(targetUrl);
    url.searchParams.set('token', token);
    return url.toString();
  } catch (error) {
    console.error('Failed to build third login callback URL:', error);
    return targetUrl;
  }
}

export function buildOauthCallbackBridgeUrl(
  callbackUrl?: string,
  thirdLogin?: string | boolean | null,
): string {
  const targetUrl = callbackUrl || '/';

  if (!isThirdLoginFlagEnabled(thirdLogin)) {
    return targetUrl;
  }

  return `/auth/signin?callbackUrl=${encodeURIComponent(targetUrl)}&thirdLogin=true`;
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
