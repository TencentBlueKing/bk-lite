import { BUILD_IN_MODEL } from '@/app/cmdb/constants/asset';
import type { ModelIconItem } from '@/app/cmdb/types/assetManage';

export type ModelIconSource = 'icons' | 'icons-realistic';

export interface IconDescriptor {
  describe?: string;
  key: string;
  url: string;
}

export interface ModelIconOption extends IconDescriptor {
  source: ModelIconSource;
  value: string;
  src: string;
}

interface IconCatalogs {
  standardIcons: IconDescriptor[];
  realisticIcons: IconDescriptor[];
}

interface ExactModelIconReference {
  source: ModelIconSource;
  url: string;
}

export const DEFAULT_MODEL_ICON_NAME = 'cc-default_默认';

const createModelIconReference = (
  source: ModelIconSource,
  url: string
) => `${source}/${url}`;

const createModelIconOption = (
  icon: IconDescriptor,
  source: ModelIconSource
): ModelIconOption => {
  const value = createModelIconReference(source, icon.url);
  return {
    ...icon,
    source,
    value,
    src: `/assets/${value}.svg`,
  };
};

const parseExactModelIconReference = (
  icon: string
): ExactModelIconReference | undefined => {
  const sources: ModelIconSource[] = ['icons-realistic', 'icons'];
  const source = sources.find((item) => icon.startsWith(`${item}/`));
  if (!source) return undefined;

  const url = icon.slice(source.length + 1);
  if (!url || url.includes('/')) return undefined;
  return { source, url };
};

const findExactIcon = (icon: string, icons: IconDescriptor[]) =>
  icons.find((item) => item.url === icon);

const findIconByKey = (icon: string, icons: IconDescriptor[]) => {
  const key = icon.split('_')[0];
  return icons.find((item) => item.key === key);
};

const resolveExactReference = (
  reference: ExactModelIconReference,
  catalogs: IconCatalogs
) => {
  const icons =
    reference.source === 'icons-realistic'
      ? catalogs.realisticIcons
      : catalogs.standardIcons;
  const icon = findExactIcon(reference.url, icons);
  return icon
    ? createModelIconReference(reference.source, icon.url)
    : undefined;
};

const resolveLegacyReference = (icon: string, catalogs: IconCatalogs) => {
  const raw = icon.startsWith('icon-') ? icon.slice('icon-'.length) : icon;
  const realisticIcon =
    findExactIcon(raw, catalogs.realisticIcons) ||
    findIconByKey(raw, catalogs.realisticIcons);
  if (realisticIcon) {
    return createModelIconReference('icons-realistic', realisticIcon.url);
  }

  const standardIcon =
    findExactIcon(raw, catalogs.standardIcons) ||
    findIconByKey(raw, catalogs.standardIcons);
  return standardIcon
    ? createModelIconReference('icons', standardIcon.url)
    : undefined;
};

const resolveConfiguredReference = (
  icon: string,
  catalogs: IconCatalogs
) => {
  const exactReference = parseExactModelIconReference(icon);
  return exactReference
    ? resolveExactReference(exactReference, catalogs)
    : resolveLegacyReference(icon, catalogs);
};

const getDefaultModelIconReference = (catalogs: IconCatalogs) =>
  resolveLegacyReference(DEFAULT_MODEL_ICON_NAME, catalogs) ||
  createModelIconReference('icons-realistic', DEFAULT_MODEL_ICON_NAME);

export const createModelIconOptions = (
  standardIcons: IconDescriptor[],
  realisticIcons: IconDescriptor[]
) => [
  ...realisticIcons.map((icon) =>
    createModelIconOption(icon, 'icons-realistic')
  ),
  ...standardIcons.map((icon) => createModelIconOption(icon, 'icons')),
];

export const resolveModelIconReference = (
  model: ModelIconItem,
  standardIcons: IconDescriptor[],
  realisticIcons: IconDescriptor[]
) => {
  const catalogs = { standardIcons, realisticIcons };
  const configuredReference = model.icn
    ? resolveConfiguredReference(model.icn, catalogs)
    : undefined;
  if (configuredReference) return configuredReference;

  const builtInIconKey = BUILD_IN_MODEL.find(
    (item) => item.key === model.model_id
  )?.icon;
  const builtInReference = builtInIconKey
    ? resolveLegacyReference(builtInIconKey, catalogs)
    : undefined;

  return builtInReference || getDefaultModelIconReference(catalogs);
};
