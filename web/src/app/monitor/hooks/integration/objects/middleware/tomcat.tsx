export const useTomcatConfig = () => {
  return {
    instance_type: 'tomcat',
    dashboardDisplay: [],
    groupIds: {},
    collectTypes: {
      'Tomcat-JMX': 'jmx',
      Tomcat: 'middleware',
    },
  };
};
