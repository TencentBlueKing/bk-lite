import axios from 'axios';

export const getRequestErrorMessage = (
  error: unknown,
  fallbackMessage: string,
): string => {
  if (axios.isAxiosError(error)) {
    const responseData = error.response?.data;
    if (typeof responseData?.message === 'string' && responseData.message.trim()) {
      return responseData.message.trim();
    }
    if (typeof responseData?.detail === 'string' && responseData.detail.trim()) {
      return responseData.detail.trim();
    }
  }

  if (error instanceof Error && error.message.trim()) {
    return error.message.trim();
  }

  if (typeof error === 'string' && error.trim()) {
    return error.trim();
  }

  return fallbackMessage;
};