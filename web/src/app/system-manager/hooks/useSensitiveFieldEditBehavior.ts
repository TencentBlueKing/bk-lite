'use client';

import { useState, useCallback } from 'react';
import type { FormInstance } from 'antd';

export type SensitiveFieldMode = 'plain' | 'overwrite';

export interface SensitiveFieldState {
  isEditing: boolean;
  mode: SensitiveFieldMode;
  initialValue?: string;
  isDirty: boolean;
}

export function useSensitiveFieldEditBehavior(formRef: React.RefObject<FormInstance | null>) {
  const [fieldsState, setFieldsState] = useState<Record<string, SensitiveFieldState>>({});

  // CE default simply acts as plain mode, but we expose the mode parameter so EE can override.
  const initField = useCallback((field: string, initialValue: string | undefined, mode: SensitiveFieldMode = 'plain') => {
    setFieldsState(prev => ({
      ...prev,
      [field]: {
        isEditing: false,
        mode,
        initialValue,
        isDirty: false,
      }
    }));
  }, []);

  const handleEditClick = useCallback((field: string) => {
    if (!formRef.current) return;
    const currentVal = formRef.current.getFieldValue(field);
    setFieldsState(prev => ({
      ...prev,
      [field]: {
        ...prev[field],
        isEditing: true,
        initialValue: prev[field]?.initialValue ?? currentVal,
      }
    }));
    formRef.current.setFieldsValue({ [field]: '' });
  }, [formRef]);

  const handleConfirmEdit = useCallback((field: string) => {
    const confirmedValue = formRef.current?.getFieldValue(field);
    setFieldsState(prev => ({
      ...prev,
      [field]: {
        ...prev[field],
        isEditing: false,
        initialValue: confirmedValue,
        isDirty: true,
      }
    }));
  }, [formRef]);

  const handleCancelEdit = useCallback((field: string) => {
    const state = fieldsState[field];
    if (state && formRef.current) {
      formRef.current.setFieldsValue({ [field]: state.initialValue });
      setFieldsState(prev => ({
        ...prev,
        [field]: {
          ...prev[field],
          isEditing: false,
          isDirty: false,
        }
      }));
    }
  }, [fieldsState, formRef]);

  const isAnyFieldEditing = useCallback(() => {
    return Object.values(fieldsState).some(state => state.isEditing);
  }, [fieldsState]);

  // Strip untouched values in overwrite mode
  const cleanPayload = useCallback((payload: Record<string, any>, sensitiveFields: string[]) => {
    const cleaned = { ...payload };
    sensitiveFields.forEach(field => {
      const state = fieldsState[field];
      if (state?.mode === 'overwrite' && !state.isDirty) {
        delete cleaned[field];
      }
    });
    return cleaned;
  }, [fieldsState]);

  const updateMode = useCallback((field: string, mode: SensitiveFieldMode) => {
    setFieldsState(prev => {
      if (!prev[field]) return prev;
      if (prev[field].mode === mode) return prev;
      return {
        ...prev,
        [field]: {
          ...prev[field],
          mode,
        }
      };
    });
  }, []);

  return {
    fieldsState,
    initField,
    updateMode,
    handleEditClick,
    handleConfirmEdit,
    handleCancelEdit,
    isAnyFieldEditing,
    cleanPayload,
  };
}
