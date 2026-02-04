import { useState } from 'react';
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

export const useTaskForm = ({
  editId,
  onSuccess,
  onClose,
  formatValues,
}: UseTaskFormProps) => {
  const { t } = useTranslation();
  const collectApi = useCollectApi();
  const [form] = Form.useForm();
  const [loading, setLoading] = useState(false);
  const [submitLoading, setSubmitLoading] = useState(false);

  const formatCycleValue = (values: any) => {
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
  };

  const fetchTaskDetail = async (id: number) => {
    try {
      setLoading(true);
      const data = await collectApi.getCollectDetail(id.toString());
      useAssetManageStore.getState().setScanCycleType(data.cycle_value_type || null);
      const cycleFields = getCycleFormValues(data);
      form.setFieldsValue({
        ...data,
        taskName: data.name,
        instId: data.instances?.[0]?._id,
        ...cycleFields,
      });
      return data;
    } catch (error) {
      console.error('Failed to fetch task detail:', error);
    } finally {
      setLoading(false);
    }
  };

  const onFinish = async (values: any) => {
    try {
      setSubmitLoading(true);
      const params = formatValues(values);
      if (editId) {
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
      onClose();
    } catch (error) {
      console.error('Failed to save task:', error);
    } finally {
      setSubmitLoading(false);
    }
  };

  return {
    form,
    loading,
    submitLoading,
    fetchTaskDetail,
    onFinish,
    formatCycleValue,
  };
};
