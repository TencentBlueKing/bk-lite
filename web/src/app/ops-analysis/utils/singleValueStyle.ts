export type SingleValueIconSource = 'builtin' | 'upload';
export type SingleValueIconPosition = 'left' | 'right';
export type SingleValueIconSize = 'small' | 'medium' | 'large';
export type SingleValueContentAlign = 'left' | 'center' | 'right';

/** 单值组件样式。字段缺省时渲染保持旧行为。 */
export interface SingleValueStyleConfig {
  showIcon?: boolean;
  iconSource?: SingleValueIconSource;
  /** 内置图标 key，对应 CMDB 模型图标库 */
  iconKey?: string;
  /** 上传图片的 data URL */
  iconImage?: string;
  iconPosition?: SingleValueIconPosition;
  iconSize?: SingleValueIconSize;
  align?: SingleValueContentAlign;
}

/** 编辑态。开关打开后来源默认内置图标；另一边已选内容仍留在草稿里。 */
export interface SingleValueStyleDraft {
  showIcon: boolean;
  iconSource?: SingleValueIconSource;
  iconKey: string;
  iconImage: string;
  iconPosition: SingleValueIconPosition;
  iconSize: SingleValueIconSize;
  /** 未配置时为 undefined，由各主题沿用旧对齐 */
  align?: SingleValueContentAlign;
}

export const SINGLE_VALUE_ICON_MAX_BYTES = 100 * 1024;

/**
 * 图标高度相对数值字号。大档略大于数值字号，
 * 中档略小、小档更小。
 */
export const SINGLE_VALUE_ICON_FONT_RATIO: Record<SingleValueIconSize, number> = {
  small: 0.6,
  medium: 0.85,
  large: 1.15,
};

/** 约三分之一数字字宽（≈0.2em），随字号缩放 */
export const SINGLE_VALUE_ICON_GAP_RATIO = 0.2;
/** 窄卡片先把图标收到这个比例，再窄则隐藏 */
export const SINGLE_VALUE_ICON_MIN_SCALE = 0.45;

const ICON_MIME = new Set([
  'image/png',
  'image/jpeg',
  'image/webp',
  'image/svg+xml',
]);

const ICON_MIME_BY_EXTENSION: Record<string, string> = {
  png: 'image/png',
  jpg: 'image/jpeg',
  jpeg: 'image/jpeg',
  webp: 'image/webp',
  svg: 'image/svg+xml',
};

const singleValueIconExtension = (name: string) => {
  const match = /\.([^.]+)$/.exec(name.trim());
  return match?.[1]?.toLowerCase() ?? '';
};

const roundTenth = (value: number) => Math.round(value * 10) / 10;

export const isSingleValueIconDataUrl = (value: string) =>
  /^data:image\/(?:png|jpeg|webp|svg\+xml)[;,]/i.test(value);

const readIconSource = (
  style: SingleValueStyleConfig | null | undefined,
  iconKey: string,
  iconImage: string,
): SingleValueIconSource | undefined => {
  if (style?.iconSource === 'upload' || style?.iconSource === 'builtin') {
    return style.iconSource;
  }
  if (iconKey) return 'builtin';
  if (isSingleValueIconDataUrl(iconImage)) return 'upload';
  // 只打开了图标、还没选具体资源：重开时仍停在内置图标，不回到两边都不选。
  if (style?.showIcon === true) return 'builtin';
  return undefined;
};

export const readSingleValueStyle = (
  style?: SingleValueStyleConfig | null,
): SingleValueStyleDraft => {
  const iconKey = typeof style?.iconKey === 'string' ? style.iconKey.trim() : '';
  const iconImage = typeof style?.iconImage === 'string' ? style.iconImage.trim() : '';
  return {
    showIcon: style?.showIcon === true,
    iconSource: readIconSource(style, iconKey, iconImage),
    iconKey,
    iconImage,
    iconPosition: style?.iconPosition === 'right' ? 'right' : 'left',
    iconSize:
      style?.iconSize === 'small' || style?.iconSize === 'large'
        ? style.iconSize
        : 'medium',
    align:
      style?.align === 'left' || style?.align === 'center' || style?.align === 'right'
        ? style.align
        : undefined,
  };
};

export const validateSingleValueIconFile = (file: {
  name: string;
  type: string;
  size: number;
}): 'type' | 'size' | null => {
  // 浏览器给出的 MIME 必须在白名单里。只有空类型才按扩展名放行。
  const typeOk = file.type
    ? ICON_MIME.has(file.type)
    : Boolean(ICON_MIME_BY_EXTENSION[singleValueIconExtension(file.name)]);
  if (!typeOk) return 'type';
  if (file.size > SINGLE_VALUE_ICON_MAX_BYTES) return 'size';
  return null;
};

/** FileReader 对空 type 会写成 data:;base64。扩展名合法时补上对应 MIME。 */
export const ensureSingleValueIconFileType = (file: File): File => {
  if (file.type) return file;
  const mime = ICON_MIME_BY_EXTENSION[singleValueIconExtension(file.name)];
  if (!mime) return file;
  return new File([file], file.name, {
    type: mime,
    lastModified: file.lastModified,
  });
};

export const resolveSingleValueIconSrc = (
  style: SingleValueStyleDraft,
  resolveBuiltin: (iconKey: string) => string,
): string | null => {
  if (!style.showIcon || !style.iconSource) return null;
  if (style.iconSource === 'upload') {
    return isSingleValueIconDataUrl(style.iconImage) ? style.iconImage : null;
  }
  if (!style.iconKey) return null;
  const src = resolveBuiltin(style.iconKey);
  return src || null;
};

export interface ResolveSingleValueIconBoxInput {
  rowWidth: number;
  fontSize: number;
  textWidth: number;
  size: SingleValueIconSize;
  /** 图片宽高比。未知时按正方形，量到后再收窄。 */
  aspect?: number;
}

export interface SingleValueIconBox {
  visible: boolean;
  /** 图标高度 */
  size: number;
  /** 图标占位宽度，按图片宽高比 */
  width: number;
  gap: number;
}

/**
 * 图标跟随数值字号。宽度不够时先缩小图标，再隐藏，把宽度留给数值。
 * 尚未量到行宽时保持可见，避免首帧把图标丢掉。
 */
export const resolveSingleValueIconBox = ({
  rowWidth,
  fontSize,
  textWidth,
  size,
  aspect = 1,
}: ResolveSingleValueIconBoxInput): SingleValueIconBox => {
  const desired = Math.max(0, fontSize) * SINGLE_VALUE_ICON_FONT_RATIO[size];
  const safeAspect = aspect > 0 && Number.isFinite(aspect) ? aspect : 1;
  const gap = Math.max(0, fontSize) * SINGLE_VALUE_ICON_GAP_RATIO;
  const hidden = { visible: false, size: 0, width: 0, gap: 0 };
  if (!(rowWidth > 0) || !(fontSize > 0)) {
    return {
      visible: true,
      size: roundTenth(desired),
      width: roundTenth(desired * safeAspect),
      gap: roundTenth(gap),
    };
  }

  const minHeight = desired * SINGLE_VALUE_ICON_MIN_SCALE;
  const available = rowWidth - Math.max(0, textWidth) - gap;
  const desiredWidth = desired * safeAspect;
  if (available >= desiredWidth) {
    return {
      visible: true,
      size: roundTenth(desired),
      width: roundTenth(desiredWidth),
      gap: roundTenth(gap),
    };
  }
  if (available >= minHeight * safeAspect) {
    return {
      visible: true,
      size: roundTenth(available / safeAspect),
      width: roundTenth(available),
      gap: roundTenth(gap),
    };
  }
  return hidden;
};

/**
 * 只写入当前来源。编辑态里另一边的选择留在草稿，不进配置。
 * 来源未显式选择时不推断，避免把暂存的另一边写进去。
 * 对齐只有用户点过（草稿里有值）才写入，缺省不把「左」落库。
 */
export const persistSingleValueStyle = (
  style: SingleValueStyleConfig | undefined,
): SingleValueStyleConfig | undefined => {
  const iconKey = typeof style?.iconKey === 'string' ? style.iconKey.trim() : '';
  const iconImage = typeof style?.iconImage === 'string' ? style.iconImage.trim() : '';
  const source = style?.iconSource === 'upload' || style?.iconSource === 'builtin'
    ? style.iconSource
    : undefined;
  const next: SingleValueStyleConfig = {};

  if (style?.showIcon === true) {
    next.showIcon = true;
    if (source === 'upload' && isSingleValueIconDataUrl(iconImage)) {
      next.iconSource = 'upload';
      next.iconImage = iconImage;
    } else if (source === 'builtin' && iconKey) {
      next.iconKey = iconKey;
    }
    if (style.iconPosition === 'right') next.iconPosition = 'right';
    if (style.iconSize === 'small' || style.iconSize === 'large') {
      next.iconSize = style.iconSize;
    }
  }

  if (style?.align === 'left' || style?.align === 'center' || style?.align === 'right') {
    next.align = style.align;
  }

  return Object.keys(next).length > 0 ? next : undefined;
};
