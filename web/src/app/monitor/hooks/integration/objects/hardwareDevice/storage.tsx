export const useStorageConfig = () => {
  return {
    instance_type: 'storage',
    dashboardDisplay: [
      {
        indexId: 'sangfor_eds_cluster_host_num',
        displayType: 'single',
        sortIndex: 0,
        displayDimension: [],
        style: {
          height: '200px',
          width: '24%'
        }
      },
      {
        indexId: 'sangfor_eds_cluster_physical_usage_percent',
        displayType: 'single',
        sortIndex: 1,
        displayDimension: [],
        style: {
          height: '200px',
          width: '24%'
        }
      },
      {
        indexId: 'sangfor_eds_cluster_total_physical_bytes',
        displayType: 'single',
        sortIndex: 2,
        displayDimension: [],
        style: {
          height: '200px',
          width: '24%'
        }
      },
      {
        indexId: 'sangfor_eds_cluster_used_physical_bytes',
        displayType: 'single',
        sortIndex: 3,
        displayDimension: [],
        style: {
          height: '200px',
          width: '24%'
        }
      },
      {
        indexId: 'sangfor_eds_block_pool_usage_rate',
        displayType: 'single',
        sortIndex: 4,
        displayDimension: [],
        style: {
          height: '200px',
          width: '24%'
        }
      },
      {
        indexId: 'sangfor_eds_capacity_pool_usage_rate',
        displayType: 'single',
        sortIndex: 5,
        displayDimension: [],
        style: {
          height: '200px',
          width: '24%'
        }
      },
      {
        indexId: 'sangfor_eds_cluster_abnormal_manage_nic_num',
        displayType: 'single',
        sortIndex: 6,
        displayDimension: [],
        style: {
          height: '200px',
          width: '24%'
        }
      },
      {
        indexId: 'sangfor_eds_disk_status',
        displayType: 'multipleIndexsTable',
        sortIndex: 7,
        displayDimension: [
          'sangfor_eds_disk_usage_rate',
          'sangfor_eds_disk_life_percent',
          'sangfor_eds_disk_bad_sector',
          'sangfor_eds_disk_size_bytes'
        ],
        style: {
          height: '400px',
          width: '100%'
        }
      }
    ],
    groupIds: {
      list: ['instance_id'],
      default: ['instance_id']
    },
    collectTypes: {
      'Storage Sangfor EDS SNMP': 'snmp_storage_sangfor_eds'
    }
  };
};
