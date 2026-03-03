'use client';

import { useState, useCallback } from 'react';
import { Form, message } from 'antd';
import type { AuthSource } from '@/app/system-manager/types/security';
import { useSecurityApi } from '@/app/system-manager/api/security';
import { enhanceAuthSourcesList } from '@/app/system-manager/utils/authSourceUtils';
import {
  SourceType,
  buildUpdatePayload,
  buildCreatePayload,
  populateFormFromSource,
  getDefaultRolesFromSource,
  getFieldsToResetOnTypeChange,
} from '@/app/system-manager/utils/authSourceFormUtils';

interface UseAuthSourceModalProps {
  authSources: AuthSource[];
  onUpdate: (sources: AuthSource[]) => void;
  t: (key: string) => string;
}

interface UseAuthSourceModalResult {
  isModalVisible: boolean;
  editingSource: AuthSource | null;
  modalLoading: boolean;
  dynamicForm: ReturnType<typeof Form.useForm>[0];
  selectedRoles: number[];
  setSelectedRoles: React.Dispatch<React.SetStateAction<number[]>>;
  handleAddAuthSource: () => void;
  handleEditSource: (source: AuthSource) => void;
  handleAuthSourceSubmit: () => Promise<void>;
  handleModalCancel: () => void;
  handleAuthSourceToggle: (source: AuthSource, enabled: boolean) => Promise<void>;
  handleSyncAuthSource: (source: AuthSource) => Promise<void>;
  handleSourceTypeChange: (newSourceType: string) => void;
}

export function useAuthSourceModal({
  authSources,
  onUpdate,
  t,
}: UseAuthSourceModalProps): UseAuthSourceModalResult {
  const [isModalVisible, setIsModalVisible] = useState(false);
  const [editingSource, setEditingSource] = useState<AuthSource | null>(null);
  const [modalLoading, setModalLoading] = useState(false);
  const [selectedRoles, setSelectedRoles] = useState<number[]>([]);
  const [dynamicForm] = Form.useForm();

  const { updateAuthSource, createAuthSource, syncAuthSource } = useSecurityApi();

  const handleAddAuthSource = useCallback(() => {
    setEditingSource(null);
    setSelectedRoles([]);
    dynamicForm.resetFields();
    setIsModalVisible(true);
  }, [dynamicForm]);

  const handleEditSource = useCallback((source: AuthSource) => {
    setEditingSource(source);
    const formValues = populateFormFromSource(source);
    const defaultRoles = getDefaultRolesFromSource(source);
    setSelectedRoles(defaultRoles);
    dynamicForm.setFieldsValue(formValues);
    setIsModalVisible(true);
  }, [dynamicForm]);

  const handleAuthSourceSubmit = useCallback(async () => {
    try {
      setModalLoading(true);
      const values = await dynamicForm.validateFields();

      if (editingSource) {
        const updateData = buildUpdatePayload(
          editingSource.source_type as SourceType,
          values,
          selectedRoles
        );
        await updateAuthSource(editingSource.id, updateData);

        const updatedSource = { ...editingSource, ...updateData };
        const enhancedSource = enhanceAuthSourcesList([updatedSource])[0];

        onUpdate(authSources.map(item =>
          item.id === editingSource.id ? enhancedSource : item
        ));

        message.success(t('common.updateSuccess'));
      } else {
        const createData = buildCreatePayload(values, selectedRoles);
        const newSource = await createAuthSource(createData);
        const enhancedSource = enhanceAuthSourcesList([newSource])[0];

        onUpdate([...authSources, enhancedSource]);
        message.success(t('common.saveSuccess'));
      }

      setIsModalVisible(false);
      setEditingSource(null);
      setSelectedRoles([]);
      dynamicForm.resetFields();
    } catch (error) {
      console.error('Failed to save auth source:', error);
      message.error(editingSource ? t('common.updateFailed') : t('common.createFailed'));
    } finally {
      setModalLoading(false);
    }
  }, [dynamicForm, editingSource, selectedRoles, authSources, onUpdate, updateAuthSource, createAuthSource, t]);

  const handleModalCancel = useCallback(() => {
    if (modalLoading) return;
    setIsModalVisible(false);
    setEditingSource(null);
    dynamicForm.resetFields();
  }, [modalLoading, dynamicForm]);

  const handleAuthSourceToggle = useCallback(async (source: AuthSource, enabled: boolean) => {
    try {
      const updateData = { ...source, enabled };
      await updateAuthSource(source.id, updateData);
      onUpdate(authSources.map(item =>
        item.id === source.id ? { ...item, enabled } : item
      ));
      message.success(t('common.saveSuccess'));
    } catch (error) {
      console.error('Failed to update auth source status:', error);
      message.error(t('common.saveFailed'));
    }
  }, [authSources, onUpdate, updateAuthSource, t]);

  const handleSyncAuthSource = useCallback(async (source: AuthSource) => {
    try {
      await syncAuthSource(source.id);
      message.success(t('system.security.syncSuccess'));
    } catch (error) {
      console.error('Failed to sync auth source:', error);
      message.error(t('system.security.syncFailed'));
    }
  }, [syncAuthSource, t]);

  const handleSourceTypeChange = useCallback((newSourceType: string) => {
    const fieldsToReset = getFieldsToResetOnTypeChange(newSourceType);
    const resetValues = fieldsToReset.reduce((acc, field) => {
      acc[field] = undefined;
      return acc;
    }, {} as Record<string, undefined>);

    dynamicForm.setFieldsValue({
      ...resetValues,
      default_roles: undefined,
      root_group: undefined,
    });
    setSelectedRoles([]);
  }, [dynamicForm]);

  return {
    isModalVisible,
    editingSource,
    modalLoading,
    dynamicForm,
    selectedRoles,
    setSelectedRoles,
    handleAddAuthSource,
    handleEditSource,
    handleAuthSourceSubmit,
    handleModalCancel,
    handleAuthSourceToggle,
    handleSyncAuthSource,
    handleSourceTypeChange,
  };
}

export function copyToClipboard(text: string, t: (key: string) => string): void {
  try {
    if (navigator?.clipboard?.writeText) {
      navigator.clipboard.writeText(text).then(() => {
        message.success(t('common.copySuccess'));
      }).catch(() => {
        message.error(t('common.copyFailed'));
      });
    } else {
      const textArea = document.createElement('textarea');
      textArea.value = text;
      document.body.appendChild(textArea);
      textArea.select();
      const successful = document.execCommand('copy');
      document.body.removeChild(textArea);

      if (successful) {
        message.success(t('common.copySuccess'));
      } else {
        message.error(t('common.copyFailed'));
      }
    }
  } catch (error) {
    console.error('Copy failed:', error);
    message.error(t('common.copyFailed'));
  }
}
