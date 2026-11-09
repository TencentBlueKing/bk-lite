import { useCallback } from 'react';
import useApiClient from '@/utils/request';
import { fetchSharedCanvasDetail } from '@/app/ops-analysis/utils/canvasDetailCache';
import type {
  CarouselDetail,
  CarouselItemInput,
  CarouselSummary,
  CarouselWriteInput,
} from '@/app/ops-analysis/types/carousel';
import type { CanvasType } from '@/app/ops-analysis/constants/canvasTypes';

const BASE = '/operation_analysis/api/canvas_carousel/';

const unwrapList = <T,>(payload: T[] | { items?: T[] } | null | undefined): T[] => {
  if (Array.isArray(payload)) {
    return payload;
  }
  return payload?.items ?? [];
};

export const useCarouselApi = () => {
  const { get, post, patch, del } = useApiClient();

  const listCarousels = useCallback(async (name?: string) => {
    const payload = await get<CarouselSummary[] | { items: CarouselSummary[] }>(BASE, {
      params: name ? { name } : undefined,
    });
    return unwrapList(payload);
  }, [get]);

  const getCarousel = useCallback(async (id: number | string) => {
    return get<CarouselDetail>(`${BASE}${id}/`);
  }, [get]);

  const createCarousel = useCallback(async (data: CarouselWriteInput) => {
    return post<CarouselDetail>(BASE, data);
  }, [post]);

  const updateCarousel = useCallback(async (
    id: number | string,
    data: CarouselWriteInput | Pick<CarouselWriteInput, 'name' | 'groups'> & { desc?: string },
  ) => {
    return patch<CarouselDetail>(`${BASE}${id}/`, data);
  }, [patch]);

  const deleteCarousel = useCallback(async (id: number | string) => {
    return del(`${BASE}${id}/`);
  }, [del]);

  const appendCarouselItem = useCallback(async (
    id: number | string,
    item: CarouselItemInput,
  ) => {
    return post<CarouselDetail>(`${BASE}${id}/append/`, item);
  }, [post]);

  const prefetchCanvasDetail = useCallback(async (
    resourceType: CanvasType,
    canvasId: number,
    signal?: AbortSignal,
  ) => {
    const endpoints: Record<CanvasType, string> = {
      dashboard: '/operation_analysis/api/dashboard/',
      topology: '/operation_analysis/api/topology/',
      architecture: '/operation_analysis/api/architecture/',
      screen: '/operation_analysis/api/screen/',
      report: '/operation_analysis/api/report/',
      networkTopology: '/operation_analysis/api/network_topology/',
    };
    return fetchSharedCanvasDetail(
      resourceType,
      canvasId,
      (requestSignal) => get(endpoints[resourceType] + `${canvasId}/`, {
        suppressErrorNotification: true,
        signal: requestSignal,
      }),
      signal,
    );
  }, [get]);

  return {
    listCarousels,
    getCarousel,
    createCarousel,
    updateCarousel,
    deleteCarousel,
    appendCarouselItem,
    prefetchCanvasDetail,
  };
};
