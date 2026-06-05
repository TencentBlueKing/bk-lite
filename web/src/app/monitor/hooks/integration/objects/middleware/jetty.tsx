export const useJettyJmxConfig = () => {
  return {
    instance_type: 'jetty',
    dashboardDisplay: [],
    groupIds: {},
    collectTypes: {
      'Jetty-JMX': 'jmx',
    },
  };
};
