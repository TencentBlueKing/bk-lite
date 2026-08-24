export type LibraryTabKey = 'win' | 'linux';

export const LIBRARY_PERMISSION_PATH = '/patch-manager/library';

const LIBRARY_ROUTES: Record<LibraryTabKey, string> = {
  win: '/patch-manager/library/windows',
  linux: '/patch-manager/library/linux',
};

export const getLibraryRoute = (tab: LibraryTabKey) => LIBRARY_ROUTES[tab];

export const LIBRARY_ROUTE_NAVIGATION = [
  { tab: 'win', title: 'Windows', url: LIBRARY_ROUTES.win },
  { tab: 'linux', title: 'Linux', url: LIBRARY_ROUTES.linux },
] as const;
