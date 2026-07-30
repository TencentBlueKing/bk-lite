import type { AxiosRequestConfig } from 'axios';

import type { TimeseriesPredictReasonParams } from '@/app/mlops/types';


export const TIMESERIES_PREDICT_REQUEST_TIMEOUT_MS = 300_000;

export interface TimeseriesPredictRequest {
  url: string;
  data: TimeseriesPredictReasonParams;
  config: AxiosRequestConfig;
}

export function buildTimeseriesPredictRequest(
  servingId: number,
  params: TimeseriesPredictReasonParams
): TimeseriesPredictRequest {
  return {
    url: `/mlops/timeseries_predict_servings/${servingId}/predict/`,
    data: params,
    config: { timeout: TIMESERIES_PREDICT_REQUEST_TIMEOUT_MS },
  };
}
