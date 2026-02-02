export const useJbossConfig = () => {
  return {
    instance_type: 'jboss',
    dashboardDisplay: [],
    tableDiaplay: [],
    groupIds: {},
    collectTypes: {
      'JBoss-JMX': 'jmx',
    },
  };
};
