const CARD_HEADER_HEIGHT = 56;
const CARD_BODY_VERTICAL_PADDING = 20;
const SMALL_TABLE_HEADER_HEIGHT = 47;
export const DASHBOARD_MIN_TABLE_BODY_HEIGHT = 80;

const DASHBOARD_TABLE_CHROME_HEIGHT = (
  CARD_HEADER_HEIGHT
  + CARD_BODY_VERTICAL_PADDING
  + SMALL_TABLE_HEADER_HEIGHT
);

export const DASHBOARD_MIN_SECTION_HEIGHT = (
  DASHBOARD_TABLE_CHROME_HEIGHT + DASHBOARD_MIN_TABLE_BODY_HEIGHT
);

export const resolveDashboardSectionHeight = (availableHeight: number): number => (
  Math.max(DASHBOARD_MIN_SECTION_HEIGHT, availableHeight)
);

export const resolveDashboardTableScrollY = (sectionHeight: number): number => (
  Math.max(DASHBOARD_MIN_TABLE_BODY_HEIGHT, sectionHeight - DASHBOARD_TABLE_CHROME_HEIGHT)
);
