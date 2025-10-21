import { message } from 'antd';
import { useTranslation } from '@/utils/i18n';

export const useCopy = () => {
  const { t } = useTranslation();
  const copy = (value: string) => {
    try {
      if (navigator?.clipboard?.writeText) {
        navigator.clipboard.writeText(value);
      } else {
        const textArea = document.createElement('textarea');
        textArea.value = value;
        document.body.appendChild(textArea);
        textArea.select();
        document.execCommand('copy');
        document.body.removeChild(textArea);
      }
      message.success(t('common.copySuccess'));
    } catch (error: any) {
      message.error(error + '');
    }
  };
  return {
    copy,
  };
};
