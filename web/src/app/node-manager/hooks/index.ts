import { message } from 'antd';
import { useTranslation } from '@/utils/i18n';
export const useHandleCopy = (value: string) => {
  const { t } = useTranslation();
  const handleCopy = () => {
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
      message.success(t('common.successfulCopied'));
    } catch (error: any) {
      message.error(error + '');
    }
  };
  return {
    handleCopy,
  };
};
