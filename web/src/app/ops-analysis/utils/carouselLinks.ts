import { isScreenModeEnabled, toSearchParams, withScreenQuery } from '@/console-layout';

export const OPS_CAROUSEL_PANEL = 'carousel';

export const isCarouselPanel = (search: string | URLSearchParams | null | undefined): boolean =>
  toSearchParams(search).get('panel') === OPS_CAROUSEL_PANEL;

export const buildOpsCarouselViewHref = (
  carouselId: string | null,
  currentSearch?: string | URLSearchParams | null,
): string => {
  const params = toSearchParams(currentSearch);
  params.set('panel', OPS_CAROUSEL_PANEL);
  if (carouselId) {
    params.set('carousel', carouselId);
  } else {
    params.delete('carousel');
  }
  const query = params.toString();
  return withScreenQuery(
    `/ops-analysis/view?${query}`,
    isScreenModeEnabled(currentSearch) || isScreenModeEnabled(params),
  );
};

export const buildOpsDirectoryPanelHref = (
  currentSearch?: string | URLSearchParams | null,
): string => {
  const params = toSearchParams(currentSearch);
  params.delete('panel');
  params.delete('carousel');
  const query = params.toString();
  return withScreenQuery(
    query ? `/ops-analysis/view?${query}` : '/ops-analysis/view',
    isScreenModeEnabled(currentSearch) || isScreenModeEnabled(params),
  );
};

export type OpsAnalysisPanel = 'directory' | 'carousel';

export interface OpsAnalysisViewLocation {
  panel: OpsAnalysisPanel;
  carouselId: string | null;
}

export const resolveRequestedCarouselView = (
  search: string | URLSearchParams | null | undefined,
): OpsAnalysisViewLocation => {
  const params = toSearchParams(search);
  const carouselParam = params.get('carousel');
  return {
    panel: isCarouselPanel(params) ? 'carousel' : 'directory',
    carouselId: carouselParam && carouselParam !== 'new' ? carouselParam : null,
  };
};

/** 地址和已确认的面板不一致时：没改动直接跟上，有改动先确认。 */
export const carouselViewDecision = (
  current: OpsAnalysisViewLocation,
  requested: OpsAnalysisViewLocation,
  dirty: boolean,
): 'stay' | 'apply' | 'confirm' => {
  if (current.panel === requested.panel && current.carouselId === requested.carouselId) {
    return 'stay';
  }
  return dirty ? 'confirm' : 'apply';
};

/** 前进/后退只认最新一次确认。旧弹窗的确定和取消都不再改界面。 */
export const carouselGuardIsCurrent = (activeToken: number, eventToken: number): boolean =>
  activeToken === eventToken;
