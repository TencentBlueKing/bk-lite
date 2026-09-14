'use client';

import React, { useCallback } from 'react';
import JobHostSelectionModal, {
  type FetchHostsParams,
  type FetchHostsResult,
  type JobHostSelectionModalProps,
  type HostItem,
  type TargetSourceType,
} from '@/app/job/components/host-selection-modal';
import useJobApi from '@/app/job/api';

type RuntimeProps = Omit<JobHostSelectionModalProps, 'fetchHosts'>;

const getLastTextFilter = (params: FetchHostsParams, field: string) => {
  const values = params.filters?.[field] || [];
  const value = values[values.length - 1]?.value;
  return typeof value === 'string' && value.trim() ? value.trim() : undefined;
};

const getEnumFilterValues = (params: FetchHostsParams, field: string) => {
  const values = params.filters?.[field] || [];
  const value = values[values.length - 1]?.value;
  return Array.isArray(value) ? value : [];
};

const getOperatingSystemFilter = (params: FetchHostsParams) => {
  const values = getEnumFilterValues(params, 'os_type');
  return values.length === 1 ? values[0] : undefined;
};

export const buildNodeQueryParams = (params: FetchHostsParams) => ({
  page: params.page,
  page_size: params.pageSize,
  keyword: getLastTextFilter(params, 'keyword'),
  os: getOperatingSystemFilter(params),
});

export const buildTargetQueryParams = (params: FetchHostsParams) => ({
  page: params.page,
  page_size: params.pageSize,
  search: getLastTextFilter(params, 'keyword'),
  os_type: getOperatingSystemFilter(params),
});

const JobHostSelectionModalRuntime: React.FC<RuntimeProps> = (props) => {
  const { getTargetList, queryNodes } = useJobApi();

  const fetchHosts = useCallback(
    async ({
      page,
      pageSize,
      filters,
      source,
      signal,
    }: FetchHostsParams): Promise<FetchHostsResult> => {
      if (source === 'node_manager') {
        const res = await queryNodes(buildNodeQueryParams({ page, pageSize, filters, source, signal }), { signal });

        return {
          items: (res.data?.items || []).map<HostItem>((node) => ({
            key: node.id,
            hostName: node.name,
            ipAddress: node.ip,
            cloudRegion: node.cloud_region_name || '-',
            osType: node.os_type || '-',
            currentDriver: '-',
          })),
          total: res.data?.count || 0,
        };
      }

      const res = await getTargetList(buildTargetQueryParams({ page, pageSize, filters, source, signal }), { signal });

      return {
        items: (res.items || []).map((target) => ({
          key: String(target.id),
          hostName: target.name,
          ipAddress: target.ip,
          cloudRegion: target.cloud_region_name || '-',
          osType: target.os_type_display || target.os_type || '-',
          currentDriver: target.driver,
        })),
        total: res.count || 0,
      };
    },
    [getTargetList, queryNodes],
  );

  return <JobHostSelectionModal {...props} fetchHosts={fetchHosts} />;
};

export type { HostItem, TargetSourceType };
export default JobHostSelectionModalRuntime;
