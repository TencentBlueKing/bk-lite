export const useElasticSearchConfig = () => {
  return {
    instance_type: 'elasticsearch',
    dashboardDisplay: [],
    groupIds: {},
    collectTypes: {
      'ElasticSearch-Exporter': 'exporter',
      ElasticSearch: 'database'
    }
  };
};
