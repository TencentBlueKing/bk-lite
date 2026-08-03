import type { ModelIconItem } from '@/app/cmdb/types/assetManage';
import {
  createModelIconOptions,
  DEFAULT_MODEL_ICON_NAME,
  resolveModelIconReference,
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

const normalizeSvgIconList = (data: string[]) =>
  data.map((item) => {
    const url = item.replace(/\.\//g, '').replace(/\.svg/g, '');
    return {
      url,
      key: url.split('_')[0],
      describe: url.split('_')[1],
    };
  });

const standardIconList = normalizeSvgIconList(
  require.context('../../../../public/assets/icons', false, /\.svg$/).keys()
);

const realisticIconList = normalizeSvgIconList(
  require
    .context('../../../../public/assets/icons-realistic', false, /\.svg$/)
    .keys()
);

export const iconList = createModelIconOptions(
  standardIconList,
  realisticIconList
);

const resolveReference = (model: ModelIconItem) =>
  resolveModelIconReference(model, standardIconList, realisticIconList);

export const DEFAULT_MODEL_ICON_URL = `/assets/${resolveReference({
  icn: DEFAULT_MODEL_ICON_NAME,
  model_id: '',
})}.svg`;

const iconUrlCache = new Map<string, string>();

export const getSelectedModelIconValue = (icon: string) =>
  resolveReference({ icn: icon, model_id: '' });

export const getModelIconUrl = (model: ModelIconItem) => {
  const cacheKey = `${model.icn || ''}|${model.model_id || ''}`;
  const cached = iconUrlCache.get(cacheKey);
  if (cached) return cached;

  const iconUrl = `/assets/${resolveReference(model)}.svg`;
  iconUrlCache.set(cacheKey, iconUrl);
  return iconUrl;
};

// 兼容现有拓扑和图表调用方，页面图片请优先使用 ModelIcon。
export const getIconUrl = getModelIconUrl;
