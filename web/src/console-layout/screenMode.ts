type ScreenModeStorage = Pick<Storage, 'getItem' | 'setItem' | 'removeItem'>;

const SCREEN_QUERY_PARAM = 'screen';
const SCREEN_MODE_BACKUP_KEY = 'bk.console.screenMode';
const SCREEN_MODE_PENDING_KEY = 'bk.console.screenMode.pending';

export const toSearchParams = (
  search: string | URLSearchParams | null | undefined,
): URLSearchParams => {
  if (!search) {
    return new URLSearchParams();
  }
  if (typeof search === 'string') {
    return new URLSearchParams(search.startsWith('?') ? search.slice(1) : search);
  }
  return new URLSearchParams(search);
};

export const isScreenModeEnabled = (
  search: string | URLSearchParams | null | undefined,
): boolean => {
  const value = toSearchParams(search).get(SCREEN_QUERY_PARAM);
  if (!value) {
    return false;
  }
  const normalized = value.trim().toLowerCase();
  return normalized === 'true' || normalized === '1';
};

export const withScreenQuery = (
  href: string,
  screenMode: boolean,
  currentOrigin?: string,
): string => {
  if (!screenMode || !href) {
    return href;
  }

  if (href.startsWith('//')) {
    return href;
  }

  let nextHref = href;
  if (/^https?:\/\//i.test(href)) {
    const origin = currentOrigin
      ?? (typeof window !== 'undefined' ? window.location.origin : '');
    if (!origin) {
      return href;
    }
    try {
      const url = new URL(href);
      if (url.origin !== origin) {
        return href;
      }
      nextHref = `${url.pathname}${url.search}${url.hash}`;
    } catch {
      return href;
    }
  }

  const hashIndex = nextHref.indexOf('#');
  const hash = hashIndex >= 0 ? nextHref.slice(hashIndex) : '';
  const withoutHash = hashIndex >= 0 ? nextHref.slice(0, hashIndex) : nextHref;
  const queryIndex = withoutHash.indexOf('?');
  const pathname = queryIndex >= 0 ? withoutHash.slice(0, queryIndex) : withoutHash;
  const search = queryIndex >= 0 ? withoutHash.slice(queryIndex + 1) : '';
  const params = new URLSearchParams(search);

  if (!isScreenModeEnabled(params)) {
    params.set(SCREEN_QUERY_PARAM, 'true');
  }

  const nextSearch = params.toString();
  return `${pathname}${nextSearch ? `?${nextSearch}` : ''}${hash}`;
};

export const applyScreenAwareHref = (
  href: string,
  currentSearch?: string | URLSearchParams | null,
): string => withScreenQuery(href, isScreenModeEnabled(currentSearch));

interface SameOriginNavigationInput {
  currentSearch?: string | URLSearchParams | null;
  preferNewTab?: boolean;
  explicitNewWindow?: boolean;
}

export const resolveSameOriginNavigation = (
  href: string,
  input: SameOriginNavigationInput = {},
): { href: string; mode: 'sameFrame' | 'newTab' } => {
  if (input.explicitNewWindow) {
    return { href, mode: 'newTab' };
  }

  const screenMode = isScreenModeEnabled(input.currentSearch);
  if (input.preferNewTab && !screenMode) {
    return { href, mode: 'newTab' };
  }

  return {
    href: withScreenQuery(href, screenMode),
    mode: 'sameFrame',
  };
};

export const applySameOriginNavigation = (
  href: string,
  input: SameOriginNavigationInput = {},
): void => {
  const next = resolveSameOriginNavigation(href, input);
  if (typeof window === 'undefined') {
    return;
  }
  if (next.mode === 'newTab') {
    window.open(next.href, '_blank', 'noopener,noreferrer');
    return;
  }
  window.location.href = next.href;
};

const readFlag = (storage: ScreenModeStorage, key: string): boolean => {
  try {
    return storage.getItem(key) === '1';
  } catch {
    return false;
  }
};

const writeFlag = (storage: ScreenModeStorage, key: string, enabled: boolean): void => {
  try {
    if (enabled) {
      storage.setItem(key, '1');
      return;
    }
    storage.removeItem(key);
  } catch {
    // sessionStorage may be blocked in some iframe sandboxes; skip persistence.
  }
};

export const syncScreenModePersistence = (input: {
  pathname: string;
  search: string;
  isAuthRoute: boolean;
  storage: ScreenModeStorage;
}): { restoreHref: string | null } => {
  const { pathname, search, isAuthRoute, storage } = input;
  const screenMode = isScreenModeEnabled(search);

  if (screenMode) {
    writeFlag(storage, SCREEN_MODE_BACKUP_KEY, true);
    // Auth URLs that already have screen still need pending: login success
    // often lands on a default callback without the query.
    writeFlag(storage, SCREEN_MODE_PENDING_KEY, isAuthRoute);
    return { restoreHref: null };
  }

  const backup = readFlag(storage, SCREEN_MODE_BACKUP_KEY);

  if (isAuthRoute) {
    if (backup) {
      writeFlag(storage, SCREEN_MODE_PENDING_KEY, true);
    }
    return { restoreHref: null };
  }

  const pending = readFlag(storage, SCREEN_MODE_PENDING_KEY);
  if (backup && pending) {
    writeFlag(storage, SCREEN_MODE_PENDING_KEY, false);
    return {
      restoreHref: withScreenQuery(`${pathname}${search || ''}`, true),
    };
  }

  writeFlag(storage, SCREEN_MODE_BACKUP_KEY, false);
  writeFlag(storage, SCREEN_MODE_PENDING_KEY, false);
  return { restoreHref: null };
};
