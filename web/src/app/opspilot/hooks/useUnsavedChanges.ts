import { useEffect, useRef } from 'react';
import { Modal } from 'antd';
import { useTranslation } from '@/utils/i18n';
import { useRouter } from 'next/navigation';

interface UseUnsavedChangesOptions {
  hasUnsavedChanges: boolean;
  onSave?: () => Promise<void> | void;
  message?: string;
}

/**
 * Custom hook to handle unsaved changes warning when user tries to leave the page
 * @param hasUnsavedChanges - Boolean indicating if there are unsaved changes
 * @param onSave - Optional callback to save changes
 * @param message - Custom warning message
 */
export const useUnsavedChanges = ({
  hasUnsavedChanges,
  onSave,
  message
}: UseUnsavedChangesOptions) => {
  const { t } = useTranslation();
  const router = useRouter();
  const isNavigatingRef = useRef(false);

  const defaultMessage = message || t('chatflow.unsavedChangesWarning');

  // Handle browser refresh/close
  useEffect(() => {
    const handleBeforeUnload = (event: BeforeUnloadEvent) => {
      if (hasUnsavedChanges && !isNavigatingRef.current) {
        event.preventDefault();
        event.returnValue = defaultMessage;
        return defaultMessage;
      }
    };

    window.addEventListener('beforeunload', handleBeforeUnload);

    return () => {
      window.removeEventListener('beforeunload', handleBeforeUnload);
    };
  }, [hasUnsavedChanges, defaultMessage]);

  // Handle route navigation
  useEffect(() => {
    const originalPush = router.push;
    const originalReplace = router.replace;
    const originalBack = router.back;

    const handleNavigation = (
      originalMethod: typeof router.push,
      ...args: Parameters<typeof router.push>
    ) => {
      if (hasUnsavedChanges && !isNavigatingRef.current) {
        Modal.confirm({
          title: t('chatflow.unsavedChanges'),
          content: defaultMessage,
          okText: onSave ? t('chatflow.saveAndLeave') : t('common.cancel'),
          cancelText: t('chatflow.leaveWithoutSaving'),
          centered: true,
          onOk: async () => {
            try {
              if (onSave) {
                await onSave();
              }
            } catch (error) {
              console.error('Save failed:', error);
              isNavigatingRef.current = false;
            }
          },
          onCancel: () => {
            // User chose to leave without saving
            isNavigatingRef.current = true;
            originalMethod.apply(router, args);
          }
        });
        return;
      }
      originalMethod.apply(router, args);
    };

    // Override router methods
    router.push = (...args) => handleNavigation(originalPush, ...args);
    router.replace = (...args) => handleNavigation(originalReplace, ...args);
    router.back = () => {
      if (hasUnsavedChanges && !isNavigatingRef.current) {
        Modal.confirm({
          title: t('chatflow.unsavedChanges'),
          content: defaultMessage,
          okText: onSave ? t('chatflow.saveAndLeave') : t('common.leave'),
          cancelText: t('common.cancel'),
          centered: true,
          onOk: async () => {
            try {
              if (onSave) {
                await onSave();
              }
              isNavigatingRef.current = true;
              originalBack();
            } catch (error) {
              console.error('Save failed:', error);
              isNavigatingRef.current = false;
            }
          }
        });
        return;
      }
      originalBack();
    };

    return () => {
      // Restore original methods
      router.push = originalPush;
      router.replace = originalReplace;
      router.back = originalBack;
    };
  }, [hasUnsavedChanges, onSave, defaultMessage, router, t]);

  // Reset navigation flag when changes are saved
  useEffect(() => {
    if (!hasUnsavedChanges) {
      isNavigatingRef.current = false;
    }
  }, [hasUnsavedChanges]);

  return {
    setNavigating: (value: boolean) => {
      isNavigatingRef.current = value;
    }
  };
};