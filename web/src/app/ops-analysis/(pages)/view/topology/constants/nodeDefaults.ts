export const NODE_DIMENSIONS = {
  ICON_NODE: {
    WIDTH: 100,
    HEIGHT: 100,
  },
  SINGLE_VALUE_NODE: {
    WIDTH: 120,
    HEIGHT: 40,
  },
  TEXT_NODE: {
    WIDTH: 120,
    HEIGHT: 40,
  },
} as const;

export const COLORS = {
  PRIMARY: '#1890FF',
  SUCCESS: '#52c41a',
  WARNING: '#fa8c16',
  ERROR: '#ff4d4f',

  TEXT: {
    PRIMARY: '#262626',
    SECONDARY: '#595959',
    DISABLED: '#bfbfbf',
    LIGHT: '#8c8c8c',
  },

  BACKGROUND: {
    WHITE: '#ffffff',
    LIGHT_GRAY: '#f5f5f5',
    GRAY: '#f0f0f0',
    TRANSPARENT: 'transparent',
  },

  BORDER: {
    DEFAULT: '#e0ddddff',
    LIGHT: '#f0f0f0',
    DARK: '#434343',
    PRIMARY: '#1890FF',
  },

  PORT: {
    STROKE: '#1890FF',
    FILL: '#FFFFFF',
  },

  EDGE: {
    DEFAULT: '#a7b5c4',
    SELECTED: '#1890FF',
  },
} as const;

export const TYPOGRAPHY = {
  FONT_FAMILY: {
    DEFAULT: 'Arial, sans-serif',
    SYSTEM: '-apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Helvetica Neue", Arial, sans-serif',
  },

  FONT_SIZE: {
    SMALL: 10,
    DEFAULT: 12,
    MEDIUM: 14,
    LARGE: 16,
    EXTRA_LARGE: 18,
    ICON_LABEL: 16,
    SINGLE_VALUE: 20,
    TEXT_NODE: 18,
  },

  FONT_WEIGHT: {
    NORMAL: '400',
    MEDIUM: '500',
    SEMIBOLD: '600',
    BOLD: '700',
  },
} as const;

export const SPACING = {
  BORDER_RADIUS: {
    SMALL: 4,
    DEFAULT: 6,
    LARGE: 8,
  },

  STROKE_WIDTH: {
    THIN: 1,
    DEFAULT: 2,
    THICK: 3,
  },

  PORT_RADIUS: 4,

  PADDING: {
    SMALL: 4,
    DEFAULT: 8,
    LARGE: 16,
  },
} as const;

export const NODE_DEFAULTS = {
  ICON_NODE: {
    width: NODE_DIMENSIONS.ICON_NODE.WIDTH,
    height: NODE_DIMENSIONS.ICON_NODE.HEIGHT,
    backgroundColor: COLORS.BACKGROUND.WHITE,
    borderColor: COLORS.BORDER.DEFAULT,
    textColor: COLORS.TEXT.PRIMARY,
    fontSize: TYPOGRAPHY.FONT_SIZE.ICON_LABEL,
    fontWeight: TYPOGRAPHY.FONT_WEIGHT.MEDIUM,
    borderRadius: SPACING.BORDER_RADIUS.DEFAULT,
    strokeWidth: SPACING.STROKE_WIDTH.THIN,
    logoType: 'default' as const,
    logoIcon: 'cc-host',
    logoUrl: '',
  },

  SINGLE_VALUE_NODE: {
    width: NODE_DIMENSIONS.SINGLE_VALUE_NODE.WIDTH,
    height: NODE_DIMENSIONS.SINGLE_VALUE_NODE.HEIGHT,
    backgroundColor: COLORS.BACKGROUND.TRANSPARENT,
    borderColor: COLORS.BACKGROUND.TRANSPARENT,
    textColor: COLORS.TEXT.PRIMARY,
    fontSize: TYPOGRAPHY.FONT_SIZE.SINGLE_VALUE,
    fontFamily: TYPOGRAPHY.FONT_FAMILY.DEFAULT,
    borderRadius: SPACING.BORDER_RADIUS.DEFAULT,
    strokeWidth: SPACING.STROKE_WIDTH.THIN,
  },

  TEXT_NODE: {
    width: NODE_DIMENSIONS.TEXT_NODE.WIDTH,
    height: NODE_DIMENSIONS.TEXT_NODE.HEIGHT,
    backgroundColor: COLORS.BACKGROUND.TRANSPARENT,
    borderColor: COLORS.BACKGROUND.TRANSPARENT,
    textColor: COLORS.TEXT.PRIMARY,
    fontSize: TYPOGRAPHY.FONT_SIZE.TEXT_NODE,
    fontWeight: TYPOGRAPHY.FONT_WEIGHT.NORMAL,
    strokeWidth: SPACING.STROKE_WIDTH.THIN,
  },

  CHART_NODE: {
    width: 400,
    height: 220,
    backgroundColor: COLORS.BACKGROUND.WHITE,
    borderColor: COLORS.BORDER.DEFAULT,
    textColor: COLORS.TEXT.PRIMARY,
    fontSize: TYPOGRAPHY.FONT_SIZE.ICON_LABEL,
    fontWeight: TYPOGRAPHY.FONT_WEIGHT.MEDIUM,
    borderRadius: SPACING.BORDER_RADIUS.DEFAULT,
    strokeWidth: SPACING.STROKE_WIDTH.THIN,
  },

  BASIC_SHAPE_NODE: {
    width: 120,
    height: 80,
    backgroundColor: 'rgba(255, 255, 255, 0.2)',
    borderColor: 'rgba(255, 255, 255, 0.2)',
    borderWidth: 1,
    lineType: 'solid' as const,
    shapeType: 'rectangle' as const,
    textColor: COLORS.TEXT.PRIMARY,
    fontSize: TYPOGRAPHY.FONT_SIZE.DEFAULT,
    fontWeight: TYPOGRAPHY.FONT_WEIGHT.NORMAL,
    borderRadius: 16,
    glassEffect: {
      enabled: true,
      blurIntensity: 15,
      glassOpacity: 0.2,
      borderOpacity: 0.2,
      shadowIntensity: '0 8px 32px 0 rgba(0, 0, 0, 0.2)'
    }
  },
} as const;

export const PORT_DEFAULTS = {
  RADIUS: SPACING.PORT_RADIUS,
  STROKE_COLOR: COLORS.PORT.STROKE,
  FILL_COLOR: COLORS.PORT.FILL,
  OPACITY: {
    HIDDEN: 0,
    VISIBLE: 1,
  },
  MAGNET: true,
} as const;


