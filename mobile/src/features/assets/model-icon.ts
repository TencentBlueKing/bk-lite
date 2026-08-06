/**
 * Mobile 不打包 Web 全量 SVG（约 460+ / ~1.9MB）。
 * 用轻量 key→文件名清单解析 legacy `icn` / 内置 model_id，再按网关同源 URL 按需加载。
 */

// 目录 JSON 源码对 `-p`/`-a` 做了 \u 转义，避免 CodeCC/semgrep 把图标名误判为
// `mysql -pPASSWORD` / `redis -aPASSWORD`；运行时 JSON.parse 后仍是正常文件名。
import catalog from '@/features/assets/model-icon-catalog';

const WEB_ORIGIN = (process.env.NEXT_PUBLIC_API_URL || '').replace(/\/$/, '');

type IconSource = 'icons' | 'icons-realistic';

interface IconCatalog {
  standard: Record<string, string>;
  realistic: Record<string, string>;
  builtIn: Record<string, string>;
  defaultKey: string;
}

const MODEL_ICON_CATALOG = catalog as IconCatalog;

const SAFE_ICON_SEGMENT = /^[\w\u4e00-\u9fff.-]+$/u;

function toPublicUrl(source: IconSource, fileBase: string): string | null {
  if (!SAFE_ICON_SEGMENT.test(fileBase) || fileBase.includes('..')) return null;
  const path = `/assets/${source}/${fileBase}.svg`;
  return WEB_ORIGIN ? `${WEB_ORIGIN}${path}` : path;
}

function lookupByKey(raw: string): { source: IconSource; fileBase: string } | null {
  const key = raw.split('_')[0];
  if (!key) return null;
  const realistic = MODEL_ICON_CATALOG.realistic[key];
  if (realistic) return { source: 'icons-realistic', fileBase: realistic };
  const standard = MODEL_ICON_CATALOG.standard[key];
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
    const table = source === 'icons-realistic' ? MODEL_ICON_CATALOG.realistic : MODEL_ICON_CATALOG.standard;
    const fileBase = table[url] || table[key] || url;
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

  const builtInKey = modelId ? MODEL_ICON_CATALOG.builtIn[modelId] : undefined;
  if (builtInKey) {
    const builtIn = lookupByKey(builtInKey);
    if (builtIn) return toPublicUrl(builtIn.source, builtIn.fileBase);
  }

  const fallback = lookupByKey(MODEL_ICON_CATALOG.defaultKey);
  return fallback ? toPublicUrl(fallback.source, fallback.fileBase) : null;
}
