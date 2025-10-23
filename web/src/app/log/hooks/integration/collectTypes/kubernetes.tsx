export const useKubernetesConfig = () => {
  const plugins = {
    Vector: {
      getConfig: () => ({
        collector: 'Vector',
        collect_type: 'kubernetes',
        icon: 'ks1',
      }),
    },
  };

  return {
    type: 'kubernetes',
    plugins,
  };
};
