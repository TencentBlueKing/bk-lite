export const usePostgresConfig = () => {
  return {
    instance_type: 'postgres',
    dashboardDisplay: [
      {
        indexId: 'postgresql_numbackends',
        displayType: 'single',
        sortIndex: 0,
        displayDimension: [],
        style: {
          height: '200px',
          width: '15%'
        }
      },
      {
        indexId: 'postgresql_xact_commit_rate',
        displayType: 'single',
        sortIndex: 1,
        displayDimension: [],
        style: {
          height: '200px',
          width: '15%'
        }
      },
      {
        indexId: 'postgresql_blks_read_rate',
        displayType: 'single',
        sortIndex: 2,
        displayDimension: [],
        style: {
          height: '200px',
          width: '15%'
        }
      },
      {
        indexId: 'postgresql_cache_hit_ratio',
        displayType: 'single',
        sortIndex: 3,
        displayDimension: [],
        style: {
          height: '200px',
          width: '15%'
        }
      },
      {
        indexId: 'postgresql_numbackends',
        displayType: 'lineChart',
        sortIndex: 4,
        displayDimension: [],
        style: {
          height: '260px',
          width: '48%'
        }
      },
      {
        indexId: 'postgresql_xact_commit_rate',
        displayType: 'lineChart',
        sortIndex: 5,
        displayDimension: [],
        style: {
          height: '260px',
          width: '48%'
        }
      },
      {
        indexId: 'postgresql_blks_hit_rate',
        displayType: 'lineChart',
        sortIndex: 6,
        displayDimension: [],
        style: {
          height: '260px',
          width: '48%'
        }
      },
      {
        indexId: 'postgresql_blks_read_rate',
        displayType: 'lineChart',
        sortIndex: 7,
        displayDimension: [],
        style: {
          height: '260px',
          width: '48%'
        }
      }
    ],
    groupIds: {},
    collectTypes: {
      'Postgres-Exporter': 'exporter',
      Postgres: 'database',
    },
  };
};
