import { useState, useCallback, useRef } from 'react';
import { useRoleApi } from '@/app/system-manager/api/application';
import type {
  PermissionsState,
  ModulePermissionConfig,
  ProviderPermissionConfig,
  PermissionConfig,
  DataPermission,
  PaginationInfo
} from '@/app/system-manager/types/permission';
import type { ModuleItem } from '@/app/system-manager/constants/application';
import {
  buildSubModulesMap,
  buildEditableModules,
  buildModuleTree
} from '@/app/system-manager/constants/application';
import {
  findPermissionInTree,
  getNestedValue
} from '@/app/system-manager/utils/permissionTreeUtils';

interface UseModuleConfigResult {
  moduleConfig: ModuleItem[];
  subModuleMap: Record<string, string[]>;
  editableModules: string[];
  moduleTree: Record<string, ModuleItem>;
  moduleConfigLoading: boolean;
  fetchModuleConfig: () => Promise<void>;
}

export function useModuleConfig(clientId: string | null): UseModuleConfigResult {
  const { getAppModules } = useRoleApi();
  const [moduleConfig, setModuleConfig] = useState<ModuleItem[]>([]);
  const [subModuleMap, setSubModuleMap] = useState<Record<string, string[]>>({});
  const [editableModules, setEditableModules] = useState<string[]>([]);
  const [moduleTree, setModuleTree] = useState<Record<string, ModuleItem>>({});
  const [moduleConfigLoading, setModuleConfigLoading] = useState(false);

  const getAppModulesRef = useRef(getAppModules);
  getAppModulesRef.current = getAppModules;
  const loadingRef = useRef(moduleConfigLoading);
  loadingRef.current = moduleConfigLoading;

  const fetchModuleConfig = useCallback(async () => {
    if (!clientId || loadingRef.current) return;

    try {
      setModuleConfigLoading(true);
      const config = await getAppModulesRef.current({ params: { app: clientId } });

      setModuleConfig(config);
      setSubModuleMap(buildSubModulesMap(config));
      setEditableModules(buildEditableModules(config));
      setModuleTree(buildModuleTree(config));
    } catch (error) {
      console.error('Failed to fetch module config:', error);
      setModuleConfig([]);
      setSubModuleMap({});
      setEditableModules([]);
      setModuleTree({});
    } finally {
      setModuleConfigLoading(false);
    }
  }, [clientId]);

  return {
    moduleConfig,
    subModuleMap,
    editableModules,
    moduleTree,
    moduleConfigLoading,
    fetchModuleConfig
  };
}

interface UsePermissionDataResult {
  loading: Record<string, boolean>;
  moduleData: Record<string, DataPermission[]>;
  pagination: Record<string, PaginationInfo>;
  loadSpecificData: (module: string, subModule?: string) => Promise<void>;
  handleTableChange: (
    paginationInfo: PaginationInfo,
    filters: unknown,
    sorter: unknown,
    module?: string,
    subModule?: string
  ) => Promise<void>;
}

export function usePermissionData(
  clientId: string | null,
  permissions: PermissionsState,
  formGroupId?: string
): UsePermissionDataResult {
  const { getAppData } = useRoleApi();
  const [loading, setLoading] = useState<Record<string, boolean>>({});
  const [moduleData, setModuleData] = useState<Record<string, DataPermission[]>>({});
  const [pagination, setPagination] = useState<Record<string, PaginationInfo>>({});

  const permissionsRef = useRef(permissions);
  permissionsRef.current = permissions;
  const loadingRef = useRef(loading);
  loadingRef.current = loading;
  const paginationRef = useRef(pagination);
  paginationRef.current = pagination;
  const getAppDataRef = useRef(getAppData);
  getAppDataRef.current = getAppData;

  const loadSpecificData = useCallback(async (module: string, subModule?: string) => {
    const dataKey = subModule ? `${module}_${subModule}` : module;

    if (loadingRef.current[dataKey]) {
      return;
    }

    try {
      setLoading(prev => ({ ...prev, [dataKey]: true }));

      const paginationInfo = paginationRef.current[dataKey] || { current: 1, pageSize: 10, total: 0 };

      const params: Record<string, unknown> = {
        app: clientId,
        module,
        child_module: subModule || '',
        page: paginationInfo.current,
        page_size: paginationInfo.pageSize,
        group_id: formGroupId
      };

      const data = await getAppDataRef.current({ params });

      const formattedData = data.items.map((item: DataPermission) => {
        let currentPermission: DataPermission | undefined;

        if (subModule) {
          const modulePermission = permissionsRef.current[module];
          if (modulePermission && typeof (modulePermission as ModulePermissionConfig).type === 'undefined') {
            const providerConfig = modulePermission as ProviderPermissionConfig;
            const subModuleConfig = findPermissionInTree(providerConfig, subModule);
            currentPermission = subModuleConfig?.specificData?.find(p => p.id === item.id);
          }
        } else {
          const moduleConfig = permissionsRef.current[module] as ModulePermissionConfig;
          currentPermission = moduleConfig.specificData?.find(p => p.id === item.id);
        }

        return {
          ...item,
          view: currentPermission?.view ?? false,
          operate: currentPermission?.operate ?? false
        };
      });

      setModuleData(prev => ({
        ...prev,
        [dataKey]: formattedData
      }));

      setPagination(prev => ({
        ...prev,
        [dataKey]: {
          ...paginationInfo,
          total: data.count
        }
      }));
    } catch (error) {
      console.error('Failed to load specific data:', error);
    } finally {
      setLoading(prev => ({ ...prev, [dataKey]: false }));
    }
  }, [clientId, formGroupId]);

  const handleTableChange = useCallback(async (
    paginationInfo: PaginationInfo,
    _filters: unknown,
    _sorter: unknown,
    module?: string,
    subModule?: string
  ) => {
    if (!module) return;

    const dataKey = subModule ? `${module}_${subModule}` : module;

    setPagination(prev => ({
      ...prev,
      [dataKey]: {
        current: paginationInfo.current,
        pageSize: paginationInfo.pageSize,
        total: prev[dataKey]?.total || 0
      }
    }));

    try {
      setLoading(prev => ({ ...prev, [dataKey]: true }));

      const params: Record<string, unknown> = {
        app: clientId,
        module,
        child_module: subModule || '',
        page: paginationInfo.current,
        page_size: paginationInfo.pageSize,
        group_id: formGroupId
      };

      const data = await getAppDataRef.current({ params });

      const formattedData = data.items.map((item: DataPermission) => {
        let currentPermission: DataPermission | undefined;
        if (subModule) {
          const providerConfig = permissionsRef.current[module] as ProviderPermissionConfig;
          const subModuleConfig = providerConfig[subModule] as PermissionConfig;
          currentPermission = subModuleConfig.specificData?.find(p => p.id === item.id);
        } else {
          const moduleConfig = permissionsRef.current[module] as ModulePermissionConfig;
          currentPermission = moduleConfig.specificData?.find(p => p.id === item.id);
        }

        return {
          ...item,
          view: currentPermission?.view ?? false,
          operate: currentPermission?.operate ?? false
        };
      });

      setModuleData(prev => ({
        ...prev,
        [dataKey]: formattedData
      }));
    } catch (error) {
      console.error('Failed to load specific data:', error);
    } finally {
      setLoading(prev => ({ ...prev, [dataKey]: false }));
    }
  }, [clientId, formGroupId]);

  return {
    loading,
    moduleData,
    pagination,
    loadSpecificData,
    handleTableChange
  };
}

interface BuildInitialPermissionsParams {
  moduleList: string[];
  hasValue: boolean;
  value: Record<string, unknown>;
  moduleTree: Record<string, ModuleItem>;
}

export function buildInitialPermissions({
  moduleList,
  hasValue,
  value,
  moduleTree
}: BuildInitialPermissionsParams): PermissionsState {
  const initialPermissions: PermissionsState = {};

  moduleList.forEach(module => {
    const config = moduleTree[module];

    if (!config) {
      initialPermissions[module] = createFlatModulePermission(hasValue, value, module);
      return;
    }

    if (config.children && config.children.length > 0) {
      const providerConfig: ProviderPermissionConfig = {};

      const buildNestedPermissions = (
        children: ModuleItem[],
        currentPath: string[] = [],
        parentConfig: ProviderPermissionConfig = providerConfig
      ) => {
        children.forEach(child => {
          const childPath = [...currentPath, child.name];

          if (!child.children || child.children.length === 0) {
            const valueConfig = hasValue && getNestedValue(value, [module, ...childPath]);
            parentConfig[child.name] = createLeafPermission(valueConfig as PermissionConfig | undefined);
          } else {
            parentConfig[child.name] = {};
            buildNestedPermissions(child.children, childPath, parentConfig[child.name] as ProviderPermissionConfig);
          }
        });
      };

      buildNestedPermissions(config.children);
      initialPermissions[module] = providerConfig;
    } else {
      initialPermissions[module] = createFlatModulePermission(hasValue, value, module);
    }
  });

  return initialPermissions;
}

function createFlatModulePermission(
  hasValue: boolean,
  value: Record<string, unknown>,
  module: string
): ModulePermissionConfig {
  const moduleValue = value[module] as ModulePermissionConfig | undefined;
  return {
    type: (hasValue && moduleValue?.type) || 'specific',
    allPermissions: {
      view: hasValue && moduleValue?.allPermissions?.view !== undefined
        ? moduleValue.allPermissions.view
        : true,
      operate: hasValue && moduleValue?.allPermissions?.operate !== undefined
        ? moduleValue.allPermissions.operate
        : true
    },
    specificData: hasValue && moduleValue?.specificData
      ? moduleValue.specificData.map((item: DataPermission) => ({
        ...item,
        operate: item.operate === true
      }))
      : []
  };
}

function createLeafPermission(valueConfig: PermissionConfig | undefined): PermissionConfig {
  return {
    type: valueConfig?.type || 'all',
    allPermissions: {
      view: valueConfig?.allPermissions?.view !== undefined
        ? valueConfig.allPermissions.view
        : true,
      operate: valueConfig?.allPermissions?.operate !== undefined
        ? valueConfig.allPermissions.operate
        : true
    },
    specificData: valueConfig?.specificData
      ? valueConfig.specificData.map((item: DataPermission) => ({
        ...item,
        operate: item.operate === true
      }))
      : []
  };
}
