import { useCallback } from 'react';

import type {
  DashboardSubscription,
  DashboardSubscriptionPayload,
  DashboardSubscriptionUpdatePayload,
} from '@/app/ops-analysis/types/dashboardSubscription';
import useApiClient from '@/utils/request';

const SUBSCRIPTION_ENDPOINT =
  '/operation_analysis/api/dashboard_subscription/';

export const useDashboardSubscriptionApi = () => {
  const { get, post, patch, del } = useApiClient();

  const listSubscriptions = useCallback(
    (dashboardId: number) =>
      get<DashboardSubscription[]>(SUBSCRIPTION_ENDPOINT, {
        params: { dashboard_id: dashboardId },
      }),
    [get],
  );

  const createSubscription = useCallback(
    (payload: DashboardSubscriptionPayload) =>
      post<DashboardSubscription>(SUBSCRIPTION_ENDPOINT, payload),
    [post],
  );

  const updateSubscription = useCallback(
    (id: number, payload: DashboardSubscriptionUpdatePayload) =>
      patch<DashboardSubscription>(
        `${SUBSCRIPTION_ENDPOINT}${id}/`,
        payload,
      ),
    [patch],
  );

  const deleteSubscription = useCallback(
    (id: number) => del(`${SUBSCRIPTION_ENDPOINT}${id}/`),
    [del],
  );

  return {
    listSubscriptions,
    createSubscription,
    updateSubscription,
    deleteSubscription,
  };
};
