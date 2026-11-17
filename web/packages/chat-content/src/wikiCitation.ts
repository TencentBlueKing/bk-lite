import type { WikiCitation } from './types';
import { applyWikiMediaDisplayUrls, collectWikiMediaLocators, isWikiMediaDisplayUrl } from './wikiMediaDisplay';

type Request = <T>(path: string, body?: unknown) => Promise<T>;

/** Hosts provide their authenticated transport; display URLs follow the same Wiki rules. */
export async function loadWikiCitation(citation: WikiCitation, request: Request): Promise<string> {
  const material = citation.kind.includes('material');
  const base = '/opspilot/wiki_mgmt';
  const result = await request<Record<string, unknown>>(
    `${base}/${material ? `material/${citation.id}/info/` : `page/${citation.id}/`}`,
  );
  const candidates = material
    ? [result.parsed_markdown, result.original, result.ai_summary]
    : [result.body];
  const markdown = candidates.find((value): value is string => typeof value === 'string' && value.length > 0) || '';
  const locators = collectWikiMediaLocators(markdown);
  if (!locators.length || (!material && !result.knowledge_base)) return markdown;
  try {
    const { urls = {} } = await request<{ urls?: Record<string, string> }>(
      `${base}/${material ? `material/${citation.id}` : `knowledge_base/${result.knowledge_base}`}/sign_media/`,
      { locators },
    );
    const usable = Object.fromEntries(locators.flatMap(locator => {
      const url = urls[locator]?.trim();
      return url && url !== locator && isWikiMediaDisplayUrl(url) ? [[locator, url]] : [];
    }));
    return applyWikiMediaDisplayUrls(markdown, usable);
  } catch {
    // A failed media refresh must not hide otherwise readable citation text.
    return markdown;
  }
}
