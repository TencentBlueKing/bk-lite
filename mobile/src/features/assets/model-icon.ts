/**
 * Mobile 不打包 Web 全量 SVG（约 460+ / ~1.9MB）。
 * 用轻量 key→文件名清单解析 legacy `icn` / 内置 model_id，再按网关同源 URL 按需加载。
 */

import { MODEL_ICON_CATALOG } from '@/features/assets/model-icon-catalog';

const WEB_ORIGIN = (process.env.NEXT_PUBLIC_API_URL || '').replace(/\/$/, '');

type IconSource = 'icons' | 'icons-realistic';

const SAFE_ICON_SEGMENT = /^[\w\u4e00-\u9fff.-]+$/u;

function toPublicUrl(source: IconSource, fileBase: string): string | null {
  if (!SAFE_ICON_SEGMENT.test(fileBase) || fileBase.includes('..')) return null;
  const path = `/assets/${source}/${fileBase}.svg`;
  return WEB_ORIGIN ? `${WEB_ORIGIN}${path}` : path;
}

function lookupByKey(raw: string): { source: IconSource; fileBase: string } | null {
  const key = raw.split('_')[0];
  if (!key) return null;
  const realistic = MODEL_ICON_CATALOG.realistic[key as keyof typeof MODEL_ICON_CATALOG.realistic];
  if (realistic) return { source: 'icons-realistic', fileBase: realistic };
  const standard = MODEL_ICON_CATALOG.standard[key as keyof typeof MODEL_ICON_CATALOG.standard];
  if (standard) return { source: 'icons', fileBase: standard };
  return null;
}

function resolveConfigured(icn: string): { source: IconSource; fileBase: string } | null {
  for (const source of ['icons-realistic', 'icons'] as const) {
    const prefix = `${source}/`;
    if (!icn.startsWith(prefix)) continue;
    const url = icn.slice(prefix.length);
    if (!url || url.includes('/') || !SAFE_ICON_SEGMENT.test(url)) return null;
    const key = url.split('_')[0];
    const catalog = source === 'icons-realistic' ? MODEL_ICON_CATALOG.realistic : MODEL_ICON_CATALOG.standard;
    const fileBase =
      (catalog[url as keyof typeof catalog] as string | undefined) ||
      (catalog[key as keyof typeof catalog] as string | undefined) ||
      url;
    return { source, fileBase };
  }

  const raw = icn.startsWith('icon-') ? icn.slice('icon-'.length) : icn;
  return lookupByKey(raw);
}

/**
 * @param icn 模型 `icn`（可为 `icons/...`、legacy `icon-cc-*` / `cc-*`）
 * @param modelId 用于 BUILD_IN_MODEL 回退
 */
export function resolveAssetModelIconUrl(icn?: string, modelId?: string): string | null {
  const value = (icn || '').trim();
  if (value.includes('..') || value.includes('//')) return null;

  const configured = value ? resolveConfigured(value) : null;
  if (configured) return toPublicUrl(configured.source, configured.fileBase);

  const builtInKey = modelId
    ? MODEL_ICON_CATALOG.builtIn[modelId as keyof typeof MODEL_ICON_CATALOG.builtIn]
    : undefined;
  if (builtInKey) {
    const builtIn = lookupByKey(builtInKey);
    if (builtIn) return toPublicUrl(builtIn.source, builtIn.fileBase);
  }

  const fallback = lookupByKey(MODEL_ICON_CATALOG.defaultKey);
  return fallback ? toPublicUrl(fallback.source, fallback.fileBase) : null;
}
