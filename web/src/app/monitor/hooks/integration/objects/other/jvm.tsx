export const useJvmConfig = () => {
  return {
    instance_type: 'jvm',
    dashboardDisplay: [],
    groupIds: {},
    collectTypes: {
      JVM: 'jmx',
    },
  };
};
