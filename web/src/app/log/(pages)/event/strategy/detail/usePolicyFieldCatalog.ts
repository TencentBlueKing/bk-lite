import { useEffect, useMemo, useRef, useState } from 'react';
import useIntegrationApi from '@/app/log/api/integration';

interface PolicyFieldCatalog {
  fields: string[];
  loading: boolean;
}

const usePolicyFieldCatalog = (
  logGroups?: React.Key[]
): PolicyFieldCatalog => {
  const { getFields } = useIntegrationApi();
  const getFieldsRef = useRef(getFields);
  const requestVersionRef = useRef(0);
  const [fields, setFields] = useState<string[]>([]);
  const [loading, setLoading] = useState(false);
  const normalizedGroups = useMemo(
    () => (logGroups || []).map(String).sort(),
    [logGroups]
  );
  const groupsKey = JSON.stringify(normalizedGroups);

  useEffect(() => {
    getFieldsRef.current = getFields;
  }, [getFields]);

  useEffect(() => {
    const requestVersion = requestVersionRef.current + 1;
    requestVersionRef.current = requestVersion;

    if (!normalizedGroups.length) {
      setFields([]);
      setLoading(false);
      return;
    }

    const controller = new AbortController();
    const endTime = Date.now();
    const startTime = endTime - 15 * 60 * 1000;
    setLoading(true);

    void getFieldsRef
      .current(
        {
          query: '*',
          start_time: new Date(startTime).toISOString(),
          end_time: new Date(endTime).toISOString(),
          log_groups: normalizedGroups
        },
        { signal: controller.signal }
      )
      .then((data) => {
        if (
          !controller.signal.aborted &&
          requestVersion === requestVersionRef.current
        ) {
          setFields(data || []);
        }
      })
      .catch(() => {
        if (
          !controller.signal.aborted &&
          requestVersion === requestVersionRef.current
        ) {
          setFields([]);
        }
      })
      .finally(() => {
        if (
          !controller.signal.aborted &&
          requestVersion === requestVersionRef.current
        ) {
          setLoading(false);
        }
      });

    return () => controller.abort();
    // groupsKey 是排序后的分组快照，避免 Form 每次渲染产生的新数组重复请求。
  }, [groupsKey]);

  return { fields, loading };
};

export default usePolicyFieldCatalog;
