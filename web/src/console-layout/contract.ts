export const CONSOLE_CHROME_LAYOUTS = ['classic', 'app-top'] as const;

export type ConsoleChromeLayout = (typeof CONSOLE_CHROME_LAYOUTS)[number];

export const DEFAULT_CONSOLE_CHROME_LAYOUT: ConsoleChromeLayout = 'classic';

/** App-top left rail and the matching header brand column. */
export const APP_TOP_SIDE_RAIL_WIDTH_PX = 200;
/** Icon-only rail when the side nav is collapsed; the hover flyout reuses the expanded width. */
export const APP_TOP_SIDE_RAIL_COLLAPSED_WIDTH_PX = 56;

export const CONSOLE_SIDE_NAV_MODES = ['expanded', 'collapsed'] as const;

export type ConsoleSideNavMode = (typeof CONSOLE_SIDE_NAV_MODES)[number];

export const DEFAULT_CONSOLE_SIDE_NAV_MODE: ConsoleSideNavMode = 'expanded';

/** Icon + label + padding + `space-x-4`. Smaller values pack every app into the bar. */
export const APP_TOP_NAV_CHIP_WIDTH_PX = 148;
export const APP_TOP_NAV_MORE_WIDTH_PX = 80;
