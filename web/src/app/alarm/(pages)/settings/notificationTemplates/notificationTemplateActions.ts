import axios from 'axios';
import { HandledRequestError } from '@/utils/request';

interface DeleteGuardFields {
  is_builtin: boolean;
  is_global: boolean;
  assignment_count: number;
}

interface DeleteErrorPayload {
  references?: unknown[];
}

export const isNotificationTemplateDeleteDisabled = (item: DeleteGuardFields) =>
  item.is_builtin || item.is_global || item.assignment_count > 0;

export const getNotificationTemplateDeleteErrorKey = (error: unknown) => {
  if (axios.isAxiosError<DeleteErrorPayload>(error)) {
    if (error.response?.status === 409 || error.response?.data?.references?.length) {
      return 'settings.notificationTemplate.inUse';
    }
  }
  if (error instanceof HandledRequestError) {
    const payload = error.payload as DeleteErrorPayload | undefined;
    if (error.status === 409 || payload?.references?.length) {
      return 'settings.notificationTemplate.inUse';
    }
  }
  return 'alarmCommon.operateFailed';
};
