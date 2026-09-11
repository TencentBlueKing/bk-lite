export { ConsoleLayoutBootstrap } from './bootstrap';
export { ConsoleLayoutProvider, useConsoleLayout, useEffectiveChromeLayout } from './provider';
export {
  APP_TOP_NAV_CHIP_WIDTH_PX,
  APP_TOP_NAV_MORE_WIDTH_PX,
  APP_TOP_SIDE_RAIL_COLLAPSED_WIDTH_PX,
  APP_TOP_SIDE_RAIL_WIDTH_PX,
  CONSOLE_SIDE_NAV_MODES,
  DEFAULT_CONSOLE_CHROME_LAYOUT,
  DEFAULT_CONSOLE_SIDE_NAV_MODE,
  CONSOLE_CHROME_LAYOUTS,
} from './contract';
export type { ConsoleChromeLayout, ConsoleSideNavMode } from './contract';
export {
  buildAppTopSideNavGroups,
  countVisibleAppSlots,
  findActiveApp,
  getAppStripOverflow,
  isAppNavActive,
  isConsoleChromeException,
  isDetailChromeContext,
  shouldHideConsoleChrome,
  shouldHideConsoleTopNav,
  resolveAppLandingHref,
  resolveAppNavigation,
  resolveEffectiveChromeLayout,
  resolveMenuNavHref,
  shouldStayOnCurrentAppPage,
  shouldShowAppTopSideNav,
  shouldShowClassicSegmentedNav,
  splitOverflowApps,
} from './resolve';
export {
  applySameOriginNavigation,
  applyScreenAwareHref,
  isScreenModeEnabled,
  resolveSameOriginNavigation,
  syncScreenModePersistence,
  toSearchParams,
  withScreenQuery,
} from './screenMode';
export { useScreenAwareRouter } from './useScreenAwareRouter';
