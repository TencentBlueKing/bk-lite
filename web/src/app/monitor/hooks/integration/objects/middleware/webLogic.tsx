export const useWebLogicConfig = () => {
  return {
    instance_type: 'weblogic',
    dashboardDisplay: [],
    groupIds: {},
    collectTypes: {
      'WebLogic-JMX': 'jmx',
    },
  };
};
