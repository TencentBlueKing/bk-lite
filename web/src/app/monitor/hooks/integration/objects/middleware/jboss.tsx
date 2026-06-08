export const useJbossConfig = () => {
  return {
    instance_type: 'jboss',
    dashboardDisplay: [],
    groupIds: {},
    collectTypes: {
      'JBoss-JMX': 'jmx',
    },
  };
};
