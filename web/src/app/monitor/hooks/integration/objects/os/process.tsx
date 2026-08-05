export const useProcessConfig = () => {
  return {
    instance_type: 'process',
    dashboardDisplay: [
      {
        indexId: 'process_alive',
        displayType: 'single',
        sortIndex: 0,
        displayDimension: ['process_name'],
        style: {
          height: '200px',
          width: '15%'
        }
      },
      {
        indexId: 'process_cpu_usage',
        displayType: 'single',
        sortIndex: 1,
        displayDimension: ['process_name'],
        style: {
          height: '200px',
          width: '15%'
        }
      },
      {
        indexId: 'process_mem_usage',
        displayType: 'single',
        sortIndex: 2,
        displayDimension: ['process_name'],
        style: {
          height: '200px',
          width: '15%'
        }
      },
      {
        indexId: 'process_port_alive',
        displayType: 'single',
        sortIndex: 3,
        displayDimension: ['process_name'],
        style: {
          height: '200px',
          width: '15%'
        }
      },
      {
        indexId: 'process_num_threads',
        displayType: 'single',
        sortIndex: 4,
        displayDimension: ['process_name'],
        style: {
          height: '200px',
          width: '15%'
        }
      },
      {
        indexId: 'process_memory_rss',
        displayType: 'single',
        sortIndex: 5,
        displayDimension: ['process_name'],
        style: {
          height: '200px',
          width: '15%'
        }
      },
      {
        indexId: 'process_num_fds',
        displayType: 'single',
        sortIndex: 6,
        displayDimension: ['process_name'],
        style: {
          height: '200px',
          width: '15%'
        }
      }
    ],
    groupIds: {
      list: ['instance_id', 'process_name'],
      default: ['instance_id', 'process_name']
    },
    collectTypes: {
      Process: 'host',
      'Process Remote': 'http'
    }
  };
};
