import { BUILD_IN_MODEL } from '@/app/cmdb/constants/asset';
import type { ModelIconItem } from '@/app/cmdb/types/assetManage';

interface IconDescriptor {
  key: string;
  url: string;
}

export const DEFAULT_MODEL_ICON_NAME = 'cc-default_默认';

const findConfiguredIcon = (
  icn: string,
  realisticIcons: IconDescriptor[]
) => {
  const raw = icn.startsWith('icon-') ? icn.slice('icon-'.length) : icn;
  const exactMatch = realisticIcons.find((item) => item.url === raw);
  if (exactMatch) return exactMatch.url;

  const key = raw.split('_')[0];
  return realisticIcons.find((item) => item.key === key)?.url;
};

export const resolveModelIconName = (
  model: ModelIconItem,
  realisticIcons: IconDescriptor[]
) => {
  const configuredIconName = model.icn
    ? findConfiguredIcon(model.icn, realisticIcons)
    : undefined;
  const builtInIconKey = BUILD_IN_MODEL.find(
    (item) => item.key === model.model_id
  )?.icon;
  const builtInIconName = builtInIconKey
    ? findConfiguredIcon(builtInIconKey, realisticIcons)
    : undefined;

  return configuredIconName || builtInIconName || DEFAULT_MODEL_ICON_NAME;
};
