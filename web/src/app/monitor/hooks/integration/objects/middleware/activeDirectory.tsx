export const useActiveDirectoryConfig = () => {
  return {
    instance_type: 'active_directory',
    dashboardDisplay: [
      {
        indexId: 'ad_ldap_successful_binds_persec',
        displayType: 'single',
        sortIndex: 0,
        displayDimension: [],
        style: {
          height: '200px',
          width: '15%'
        }
      },
      {
        indexId: 'ad_ldap_client_sessions',
        displayType: 'single',
        sortIndex: 1,
        displayDimension: [],
        style: {
          height: '200px',
          width: '15%'
        }
      },
      {
        indexId: 'ad_ldap_bind_time',
        displayType: 'single',
        sortIndex: 2,
        displayDimension: [],
        style: {
          height: '200px',
          width: '15%'
        }
      },
      {
        indexId: 'ad_ds_threads_in_use',
        displayType: 'single',
        sortIndex: 3,
        displayDimension: [],
        style: {
          height: '200px',
          width: '15%'
        }
      },
      {
        indexId: 'ad_ldap_probe_result_code',
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
      'Active Directory': 'host'
    }
  };
};
