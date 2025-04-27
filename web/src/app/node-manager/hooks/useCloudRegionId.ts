import { useMemo } from 'react';

const useCloudId = () => {
  const searchParams = new URLSearchParams(window.location.search);
  const id = searchParams.get('cloud_region_id');
  return useMemo(() => {
    if (id && typeof id === 'string') {
      return Number(id);
    }
    return 1;
  }, [id]);
};

export default useCloudId;
