'use client';

import React from 'react';
import SubscriptionDrawer, {
  type SubscriptionDrawerProps,
} from '@/components/cmdb-subscription-drawer';
import { useSubscriptionList, useSubscriptionMutation } from '@/app/cmdb/hooks/useSubscription';
import { useModelApi } from '@/app/cmdb/api';
import { useInstanceApi } from '@/app/cmdb/api/instance';
import { useCommon } from '@/app/cmdb/context/common';
import useAssetDataStore from '@/app/cmdb/store/useAssetDataStore';
import { useChannelApi } from '@/app/system-manager/api/channel';

type RuntimeProps = Omit<
  SubscriptionDrawerProps,
  'subscriptionListController' | 'subscriptionMutationController' | 'formRuntime'
>;

const CmdbSubscriptionDrawerRuntime: React.FC<RuntimeProps> = (props) => {
  const subscriptionListController = useSubscriptionList();
  const subscriptionMutationController = useSubscriptionMutation();
  const common = useCommon();
  const { getModelAttrGroupsFullInfo, getModelAssociations } = useModelApi();
  const { searchInstances } = useInstanceApi();
  const { getChannelData } = useChannelApi();
  const cloudOptions = useAssetDataStore((state) => state.cloud_list);

  return (
    <SubscriptionDrawer
      {...props}
      subscriptionListController={subscriptionListController}
      subscriptionMutationController={subscriptionMutationController}
      formRuntime={{
        userList: common?.userList || [],
        modelList: (common?.modelList || []).map((item) => ({
          model_id: item.model_id,
          model_name: item.model_name,
        })),
        cloudOptions,
        searchInstances,
        getModelAttrGroupsFullInfo,
        getModelAssociations,
        loadChannelOptions: async () => {
          const res = await getChannelData({ page: 1, page_size: 100 });
          const list = Array.isArray(res)
            ? res
            : Array.isArray(res?.items)
              ? res.items
              : Array.isArray(res?.results)
                ? res.results
                : Array.isArray(res?.data)
                  ? res.data
                  : Array.isArray(res?.data?.results)
                    ? res.data.results
                    : Array.isArray(res?.data?.items)
                      ? res.data.items
                      : [];

          return list
            .map((item: any) => ({
              label: item?.name || item?.display_name || '',
              value: Number(item?.id),
            }))
            .filter((item: { label: string; value: number }) => {
              return item.label && !Number.isNaN(item.value);
            });
        },
      }}
    />
  );
};

export default CmdbSubscriptionDrawerRuntime;
