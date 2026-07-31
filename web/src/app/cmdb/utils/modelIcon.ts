import type { ModelIconItem } from '@/app/cmdb/types/assetManage';
import {
  DEFAULT_MODEL_ICON_NAME,
  resolveModelIconName,
} from '@/app/cmdb/utils/modelIconResolver';

declare const require: {
  context: (
    path: string,
    deep?: boolean,
    filter?: RegExp
  ) => {
    keys: () => string[];
  };
};

const CMDB_MODEL_ICON_DIR = '/assets/icons-realistic';

export const DEFAULT_MODEL_ICON_URL = `${CMDB_MODEL_ICON_DIR}/${DEFAULT_MODEL_ICON_NAME}.svg`;

const normalizeSvgIconList = (data: string[]) =>
  data.map((item) => {
    const url = item.replace(/\.\//g, '').replace(/\.svg/g, '');
    return {
      url,
      key: url.split('_')[0],
      describe: url.split('_')[1],
    };
  });

export const iconList = normalizeSvgIconList(
  require.context('../../../../public/assets/icons', false, /\.svg$/).keys()
);

const realisticIconList = normalizeSvgIconList(
  require
    .context('../../../../public/assets/icons-realistic', false, /\.svg$/)
    .keys()
);
const iconUrlCache = new Map<string, string>();

export const getModelIconUrl = (model: ModelIconItem) => {
  const cacheKey = `${model.icn || ''}|${model.model_id || ''}`;
  const cached = iconUrlCache.get(cacheKey);
  if (cached) return cached;

  const iconName = resolveModelIconName(model, realisticIconList);
  const iconUrl = `${CMDB_MODEL_ICON_DIR}/${iconName}.svg`;
  iconUrlCache.set(cacheKey, iconUrl);
  return iconUrl;
};

// 兼容现有拓扑和图表调用方，页面图片请优先使用 ModelIcon。
export const getIconUrl = getModelIconUrl;
