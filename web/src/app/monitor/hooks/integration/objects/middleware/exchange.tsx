export const useExchangeConfig = () => {
  return {
    instance_type: 'exchange',
    dashboardDisplay: [
      {
        indexId: 'exchange_active_mailbox_delivery_queue_length',
        displayType: 'single',
        sortIndex: 0,
        displayDimension: ['instance'],
        style: {
          height: '200px',
          width: '15%'
        }
      },
      {
        indexId: 'exchange_poison_queue_length',
        displayType: 'single',
        sortIndex: 1,
        displayDimension: ['instance'],
        style: {
          height: '200px',
          width: '15%'
        }
      },
      {
        indexId: 'exchange_owa_current_unique_users',
        displayType: 'single',
        sortIndex: 2,
        displayDimension: [],
        style: {
          height: '200px',
          width: '15%'
        }
      },
      {
        indexId: 'exchange_owa_requests_persec',
        displayType: 'single',
        sortIndex: 3,
        displayDimension: [],
        style: {
          height: '200px',
          width: '15%'
        }
      },
      {
        indexId: 'exchange_owa_probe_result_code',
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
      Exchange: 'host'
    }
  };
};
