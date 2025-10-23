export const useCvmConfig = () => {
  return {
    instance_type: 'qcloud',
    dashboardDisplay: [],
    tableDiaplay: [
      { type: 'value', key: 'cvm_CPU_Usage' },
      { type: 'value', key: 'cvm_MemUsage' },
      { type: 'value', key: 'cvm_CvmDiskUsage' },
    ],
    groupIds: {},
    plugins: {},
  };
};
