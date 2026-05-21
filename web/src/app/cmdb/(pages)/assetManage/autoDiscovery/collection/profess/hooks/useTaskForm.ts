import { useCallback, useState } from 'react';
import { Form, message } from 'antd';
import { useTranslation } from '@/utils/i18n';
import { useCollectApi } from '@/app/cmdb/api';
import { CYCLE_OPTIONS } from '@/app/cmdb/constants/professCollection';
import dayjs from 'dayjs';
import { useAssetManageStore } from '@/app/cmdb/store';

interface UseTaskFormProps {
  modelId: string;
  editId?: number | null;
  onSuccess?: () => void;
  onClose: () => void;
  formatValues: (values: any) => any;
  initialValues: Record<string, any>;
  /**
   * 任务保存成功后的钩子。
   * 当提供时，会在 onSuccess/onClose 之前触发；
   * 返回 true 表示由调用方接管后续流程（不再自动调用 onClose），用于引导式向导。
   */
  afterSubmitSuccess?: (ctx: { values: any; editId?: number | null }) => boolean | void | Promise<boolean | void>;
}

export const getCycleFormValues = (data: any) => {
  const cycleType = data?.cycle_value_type || CYCLE_OPTIONS.ONCE;
  const cycleValue = data?.cycle_value;
  return {
    cycle: cycleType,
    ...(cycleType === CYCLE_OPTIONS.DAILY && {
      dailyTime: dayjs(cycleValue, 'HH:mm'),
    }),
    ...(cycleType === CYCLE_OPTIONS.INTERVAL && {
      intervalValue: Number(cycleValue),
      everyHours: Number(cycleValue),
    }),
  };
};

export const getCleanupFormValues = (data: any) => ({
  cleanupStrategy: data?.data_cleanup_strategy,
  cleanupDays: data?.expire_days,
});

export const useTaskForm = ({
  editId,
  onSuccess,
  onClose,
  formatValues,
  afterSubmitSuccess,
}: UseTaskFormProps) => {
  const { t } = useTranslation();
  const collectApi = useCollectApi();
  const [form] = Form.useForm();
  const [loading, setLoading] = useState(false);
  const [submitLoading, setSubmitLoading] = useState(false);

  const formatCycleValue = useCallback((values: any) => {
    const { cycle } = values;
    if (cycle === CYCLE_OPTIONS.ONCE) {
      return { value_type: 'close', value: '' };
    } else if (cycle === CYCLE_OPTIONS.INTERVAL) {
      return {
        value_type: 'cycle',
        value: values.intervalValue || values.everyHours,
      };
    } else if (cycle === CYCLE_OPTIONS.DAILY) {
      return {
        value_type: 'timing',
        value: values.dailyTime?.format('HH:mm') || '',
      };
    }
    return { value_type: 'close', value: '' };
  }, []);

  const fetchTaskDetail = useCallback(async (id: number) => {
    try {
      setLoading(true);
      const data = await collectApi.getCollectDetail(id.toString());
      // console.log('test2.5:getCollectDetail', data.cycle_value_type);
      useAssetManageStore.getState().setScanCycleType(data.cycle_value_type || null);
      const cycleFields = getCycleFormValues(data);
      const cleanupFields = getCleanupFormValues(data);

      const formattedData = {
        ...data,
        taskName: data.name,
        instId: data.instances?.[0]?._id,
        ...cycleFields,
        ...cleanupFields,
      };

      form.setFieldsValue(formattedData);
      return formattedData;
    } catch (error) {
      console.error('Failed to fetch task detail:', error);
    } finally {
      setLoading(false);
    }
  }, [collectApi, form]);

  const onFinish = useCallback(async (values: any) => {
    try {
      setSubmitLoading(true);
      const params = formatValues(values);
      if (editId) {
        // console.log('test2.3', params.scan_cycle.value_type);
        if (params.scan_cycle.value_type === "cycle") {
          await collectApi.updateCollect(editId.toString(), params);
          message.success(t('successfullyModified'));
        } else {
          message.error(t('Collection.cycleDeprecated'));
          return;
        }
      } else {
        await collectApi.createCollect(params);
        message.success(t('successfullyAdded'));
      }

      onSuccess?.();
      let takeover = false;
      if (afterSubmitSuccess) {
        const result = await afterSubmitSuccess({ values, editId });
        takeover = result === true;
      }
      if (!takeover) {
        onClose();
      }
    } catch (error) {
      console.error('Failed to save task:', error);
    } finally {
      setSubmitLoading(false);
    }
  }, [collectApi, editId, formatValues, onClose, onSuccess, afterSubmitSuccess, t]);

  return {
    form,
    loading,
    submitLoading,
    fetchTaskDetail,
    onFinish,
    formatCycleValue,
  };
};
