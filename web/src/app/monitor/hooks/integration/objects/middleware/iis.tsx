export const useIisConfig = () => {
  return {
    instance_type: 'iis',
    dashboardDisplay: [
      {
        indexId: 'iis_current_connections',
        displayType: 'single',
        sortIndex: 0,
        displayDimension: ['instance'],
        style: {
          height: '200px',
          width: '15%'
        }
      },
      {
        indexId: 'iis_total_method_requests_persec',
        displayType: 'single',
        sortIndex: 1,
        displayDimension: ['instance'],
        style: {
          height: '200px',
          width: '15%'
        }
      },
      {
        indexId: 'iis_queue_current_size',
        displayType: 'single',
        sortIndex: 2,
        displayDimension: ['instance'],
        style: {
          height: '200px',
          width: '15%'
        }
      },
      {
        indexId: 'iis_recent_worker_process_failures',
        displayType: 'single',
        sortIndex: 3,
        displayDimension: ['instance'],
        style: {
          height: '200px',
          width: '15%'
        }
      },
      {
        indexId: 'iis_site_probe_result_code',
        displayType: 'single',
        sortIndex: 4,
        displayDimension: ['endpoint'],
        style: {
          height: '200px',
          width: '15%'
        }
      }
    ],
    groupIds: {
      list: ['instance_id'],
      default: ['instance_id']
    },
    collectTypes: {
      IIS: 'host'
    }
  };
};
