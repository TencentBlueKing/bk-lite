import { useState, useEffect, useCallback } from 'react';
import { message } from 'antd';
import type { FormInstance } from 'antd';
import { useTranslation } from '@/utils/i18n';
import { useUserInfoContext } from '@/context/userInfo';
import { buildModulesMap } from '@/app/system-manager/constants/application';
import { useRoleApi } from '@/app/system-manager/api/application';
import type { ModuleItem } from '@/app/system-manager/constants/application';
import type { DataItem, PermissionRuleItem } from '@/app/system-manager/types/permission';
import {
  convertApiDataToFormData,
  convertApiDataToFormDataRecursive,
  createDefaultPermissionRule,
  transformPermissionRulesForApi
} from '@/app/system-manager/utils/permissionTreeUtils';

interface UseDataListParams {
  clientId: string | null;
}

export function useDataList({ clientId }: UseDataListParams) {
  const { t } = useTranslation();
  const [dataList, setDataList] = useState<DataItem[]>([]);
  const [loading, setLoading] = useState(false);
  const [currentPage, setCurrentPage] = useState(1);
  const [pageSize, setPageSize] = useState(20);
  const [total, setTotal] = useState(0);

  const { getGroupDataRule, deleteGroupDataRule } = useRoleApi();

  const fetchDataList = useCallback(async (search?: string) => {
    if (!clientId) return;

    setLoading(true);
    try {
      const params: Record<string, unknown> = { app: clientId, page: currentPage, page_size: pageSize };
      if (search) {
        params.search = search;
      }

      const data = await getGroupDataRule({ params });
      setDataList(data.items);
      setTotal(data.count);
    } catch (error) {
      console.error(`${t('common.fetchFailed')}:`, error);
    } finally {
      setLoading(false);
    }
  }, [clientId, currentPage, pageSize, getGroupDataRule, t]);

  useEffect(() => {
    fetchDataList();
  }, [currentPage, pageSize]);

  const handleTableChange = useCallback((page: number, size?: number) => {
    setCurrentPage(page);
    if (size) {
      setPageSize(size);
    }
  }, []);

  const handleSearch = useCallback((value: string) => {
    setCurrentPage(1);
    fetchDataList(value);
  }, [fetchDataList]);

  const handleDelete = useCallback(async (data: DataItem, id: string | null) => {
    if (!id) return;

    try {
      await deleteGroupDataRule({
        id: data.id,
        client_id: id
      });
      message.success(t('common.delSuccess'));
      fetchDataList();
    } catch (error) {
      console.error('Failed:', error);
      message.error(t('common.delFail'));
    }
  }, [deleteGroupDataRule, fetchDataList, t]);

  return {
    dataList,
    loading,
    currentPage,
    pageSize,
    total,
    fetchDataList,
    handleTableChange,
    handleSearch,
    handleDelete
  };
}

interface UseModuleConfigParams {
  clientId: string | null;
}

export function useModuleConfig({ clientId }: UseModuleConfigParams) {
  const [supportedModules, setSupportedModules] = useState<string[]>([]);
  const [moduleConfigLoading, setModuleConfigLoading] = useState(false);
  const [moduleConfigs, setModuleConfigs] = useState<ModuleItem[]>([]);

  const { getAppModules } = useRoleApi();

  const fetchAppModules = useCallback(async () => {
    if (!clientId || moduleConfigLoading) return;

    try {
      setModuleConfigLoading(true);
      const modules = await getAppModules({ params: { app: clientId } });
      const moduleNames = buildModulesMap(modules);
      setSupportedModules(moduleNames);
      setModuleConfigs(modules);
    } catch (error) {
      console.error('Failed to fetch app modules:', error);
      setSupportedModules([]);
      setModuleConfigs([]);
    } finally {
      setModuleConfigLoading(false);
    }
  }, [clientId, moduleConfigLoading, getAppModules]);

  return {
    supportedModules,
    moduleConfigLoading,
    moduleConfigs,
    fetchAppModules
  };
}

interface UseDataModalParams {
  clientId: string | null;
  supportedModules: string[];
  moduleConfigs: ModuleItem[];
  fetchAppModules: () => Promise<void>;
  fetchDataList: () => Promise<void>;
  dataForm: FormInstance;
}

export function useDataModal({
  clientId,
  supportedModules,
  moduleConfigs,
  fetchAppModules,
  fetchDataList,
  dataForm
}: UseDataModalParams) {
  const { t } = useTranslation();
  const { groups } = useUserInfoContext();

  const [dataModalOpen, setDataModalOpen] = useState(false);
  const [selectedData, setSelectedData] = useState<DataItem | null>(null);
  const [isEditing, setIsEditing] = useState(false);
  const [modalLoading, setModalLoading] = useState(false);
  const [currentGroupId, setCurrentGroupId] = useState<string>('');
  const [selectChanged, setSelectChanged] = useState(false);

  const { addGroupDataRule, updateGroupDataRule } = useRoleApi();

  useEffect(() => {
    if (currentGroupId && selectChanged) {
      const currentPermissions = dataForm.getFieldValue('permissionRule');
      dataForm.setFieldsValue({
        permissionRule: {
          ...currentPermissions,
          _forceUpdate: Date.now()
        }
      });
      setSelectChanged(false);
    }
  }, [currentGroupId, selectChanged, dataForm]);

  const showDataModal = useCallback((data: DataItem | null = null) => {
    setIsEditing(!!data);
    setSelectedData(data);
    setModalLoading(true);
    dataForm.resetFields();

    const defaultPermissionRule = createDefaultPermissionRule(supportedModules, moduleConfigs);

    if (data) {
      const formattedPermissionRule: Record<string, unknown> = {};
      if (data.rules) {
        Object.keys(data.rules).forEach(moduleKey => {
          const moduleRules = data.rules[moduleKey];

          const hasNestedStructure = typeof moduleRules === 'object' &&
            !Array.isArray(moduleRules) &&
            Object.values(moduleRules).some(val =>
              Array.isArray(val) || (val && typeof val === 'object')
            );

          if (hasNestedStructure) {
            formattedPermissionRule[moduleKey] = convertApiDataToFormDataRecursive(moduleRules);
          } else {
            const items = Array.isArray(moduleRules) ? moduleRules : [];
            formattedPermissionRule[moduleKey] = convertApiDataToFormData(items as PermissionRuleItem[]);
          }
        });
      }

      const mergedPermissionRule = { ...defaultPermissionRule, ...formattedPermissionRule };

      dataForm.setFieldsValue({
        name: data.name,
        description: data.description,
        groupId: data.group_id,
        permissionRule: mergedPermissionRule
      });

      setCurrentGroupId(data.group_id);
    } else {
      const initialGroupId = groups.length > 0 ? groups[0].id : undefined;
      dataForm.setFieldsValue({
        permissionRule: defaultPermissionRule,
        groupId: initialGroupId
      });
      setCurrentGroupId(initialGroupId || '');
    }

    fetchAppModules();

    setTimeout(() => {
      setDataModalOpen(true);
      setModalLoading(false);
    }, 0);
  }, [supportedModules, moduleConfigs, groups, dataForm, fetchAppModules]);

  const handleDataModalSubmit = useCallback(async () => {
    try {
      setModalLoading(true);
      await dataForm.validateFields();
      const values = dataForm.getFieldsValue(true);

      if (!values.permissionRule) {
        values.permissionRule = {};
      }

      const transformedRules = transformPermissionRulesForApi(
        values.permissionRule,
        supportedModules
      );

      const requestData = {
        name: values.name,
        description: values.description || '',
        group_id: values.groupId,
        group_name: groups.find(g => g.id === values.groupId)?.name || '',
        app: clientId,
        rules: transformedRules
      };

      if (isEditing && selectedData) {
        await updateGroupDataRule({
          id: selectedData.id,
          ...requestData
        });
        message.success(t('common.updateSuccess'));
      } else {
        await addGroupDataRule(requestData);
        message.success(t('common.addSuccess'));
      }

      fetchDataList();
      setDataModalOpen(false);
      dataForm.resetFields();
    } catch (error) {
      console.error('Form submission failed:', error);
      message.error(isEditing ? t('common.updateFail') : t('common.addFail'));
    } finally {
      setModalLoading(false);
    }
  }, [
    dataForm,
    supportedModules,
    groups,
    clientId,
    isEditing,
    selectedData,
    updateGroupDataRule,
    addGroupDataRule,
    fetchDataList,
    t
  ]);

  const handleModalCancel = useCallback(() => {
    setDataModalOpen(false);
    dataForm.resetFields();
    setCurrentGroupId('');
  }, [dataForm]);

  const handleGroupChange = useCallback((value: number | number[] | undefined) => {
    const groupId = Array.isArray(value) ? value[0] : value;
    if (groupId) {
      setCurrentGroupId(groupId.toString());
      setSelectChanged(true);

      const currentPermissions = dataForm.getFieldValue('permissionRule');
      if (currentPermissions) {
        dataForm.setFieldsValue({
          permissionRule: {
            ...currentPermissions,
            _timestamp: Date.now()
          }
        });
      }
    }
  }, [dataForm]);

  return {
    dataModalOpen,
    selectedData,
    isEditing,
    modalLoading,
    currentGroupId,
    showDataModal,
    handleDataModalSubmit,
    handleModalCancel,
    handleGroupChange
  };
}
