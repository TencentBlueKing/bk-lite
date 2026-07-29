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

const JobHostSelectionModalRuntime: React.FC<RuntimeProps> = (props) => {
  const { getTargetList, queryNodes } = useJobApi();

  const fetchHosts = useCallback(
    async ({
      page,
      pageSize,
      search,
      source,
    }: FetchHostsParams): Promise<FetchHostsResult> => {
      if (source === 'node_manager') {
        const res = await queryNodes({
          page,
          page_size: pageSize,
          name: search || undefined,
        });

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

      const res = await getTargetList({
        page,
        page_size: pageSize,
        search: search || undefined,
      });

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
