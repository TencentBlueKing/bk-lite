'use client';

import React from 'react';
import { useModelApi } from '@/app/cmdb/api';
import { useInstanceApi } from '@/app/cmdb/api/instance';
import { useCommon } from '@/app/cmdb/context/common';
import useAssetDataStore from '@/app/cmdb/store/useAssetDataStore';
import { useChannelApi } from '@/app/system-manager/api/channel';
import SubscriptionRuleForm, {
  type SubscriptionRuleFormRef,
  type SubscriptionRuleFormProps,
} from '@/components/cmdb-subscription-drawer';

const CmdbSubscriptionRuleFormRuntime = React.forwardRef<
  SubscriptionRuleFormRef,
  Omit<SubscriptionRuleFormProps, 'runtime'>
>((props, ref) => {
  const common = useCommon();
  const { getModelAttrGroupsFullInfo, getModelAssociations } = useModelApi();
  const { searchInstances } = useInstanceApi();
  const { getChannelData } = useChannelApi();
  const cloudOptions = useAssetDataStore((state) => state.cloud_list);

  return (
    <SubscriptionRuleForm
      {...props}
      ref={ref}
      runtime={{
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
});

CmdbSubscriptionRuleFormRuntime.displayName = 'CmdbSubscriptionRuleFormRuntime';

export type { SubscriptionRuleFormRef };
export default CmdbSubscriptionRuleFormRuntime;
