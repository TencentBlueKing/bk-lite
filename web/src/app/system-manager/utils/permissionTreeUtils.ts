/**
 * Pure utility functions for permission tree traversal and manipulation.
 */

import type {
  PermissionConfig,
  PermissionsState,
  ModulePermissionConfig,
  ProviderPermissionConfig,
  DataPermission,
  PermissionRuleItem
} from '@/app/system-manager/types/permission';
import type { ModuleItem } from '@/app/system-manager/constants/application';

/**
 * Recursively search for a permission config by target key in a nested structure.
 */
export function findPermissionInTree(
  config: ProviderPermissionConfig | Record<string, unknown>,
  targetKey: string
): PermissionConfig | undefined {
  if (!config || typeof config !== 'object') {
    return undefined;
  }

  const targetConfig = config[targetKey];
  if (
    targetConfig &&
    typeof targetConfig === 'object' &&
    targetConfig !== null &&
    typeof (targetConfig as PermissionConfig).type !== 'undefined'
  ) {
    return targetConfig as PermissionConfig;
  }

  for (const key in config) {
    const value = config[key];
    if (
      value &&
      typeof value === 'object' &&
      value !== null &&
      typeof (value as PermissionConfig).type === 'undefined'
    ) {
      const found = findPermissionInTree(value as ProviderPermissionConfig, targetKey);
      if (found) return found;
    }
  }

  return undefined;
}

/**
 * Get permission config from permissions state, handling both flat and nested structures.
 */
export function getPermissionConfig(
  permissions: PermissionsState,
  module: string,
  subModule?: string
): PermissionConfig | undefined {
  if (!subModule) {
    const modulePermission = permissions[module];
    return modulePermission && typeof (modulePermission as ModulePermissionConfig).type !== 'undefined'
      ? (modulePermission as ModulePermissionConfig)
      : undefined;
  }

  const modulePermission = permissions[module];
  if (!modulePermission || typeof (modulePermission as ModulePermissionConfig).type !== 'undefined') {
    return undefined;
  }

  return findPermissionInTree(modulePermission as ProviderPermissionConfig, subModule);
}

/**
 * Get nested value from an object by path array.
 */
export function getNestedValue<T = unknown>(obj: Record<string, unknown>, path: string[]): T | undefined {
  return path.reduce<unknown>((current, key) => {
    return current && typeof current === 'object' && key in (current as Record<string, unknown>)
      ? (current as Record<string, unknown>)[key]
      : undefined;
  }, obj) as T | undefined;
}

/**
 * Deep clone an object, handling arrays and nested objects.
 */
export function deepClone<T>(obj: T): T {
  if (obj === null || typeof obj !== 'object') return obj;
  if (Array.isArray(obj)) return obj.map(deepClone) as unknown as T;

  const cloned: Record<string, unknown> = {};
  for (const key in obj) {
    if (Object.prototype.hasOwnProperty.call(obj, key)) {
      cloned[key] = deepClone((obj as Record<string, unknown>)[key]);
    }
  }
  return cloned as T;
}

/**
 * Recursively find the first leaf node (node without children) in a module tree.
 */
export function getFirstLeafModule(module: ModuleItem): string {
  if (!module.children || module.children.length === 0) {
    return module.name;
  }
  return getFirstLeafModule(module.children[0]);
}

/**
 * Check if a subModule belongs to a module by recursively searching children.
 */
export function isSubModuleOf(
  moduleTree: Record<string, ModuleItem>,
  module: string,
  subModule: string
): boolean {
  const moduleConfig = moduleTree[module];
  if (!moduleConfig?.children) return false;

  const findInChildren = (children: ModuleItem[]): boolean => {
    for (const child of children) {
      if (child.name === subModule) {
        return true;
      }
      if (child.children && findInChildren(child.children)) {
        return true;
      }
    }
    return false;
  };

  return findInChildren(moduleConfig.children);
}

/**
 * Recursively set a permission config in a nested provider config structure.
 * Returns true if the target was found and updated.
 */
export function setNestedPermissionConfig(
  config: ProviderPermissionConfig,
  targetSubModule: string,
  newConfig: PermissionConfig
): boolean {
  if (
    config[targetSubModule] &&
    typeof config[targetSubModule] === 'object' &&
    (config[targetSubModule] as PermissionConfig).type !== undefined
  ) {
    config[targetSubModule] = newConfig;
    return true;
  }

  for (const key in config) {
    const value = config[key];
    if (
      value &&
      typeof value === 'object' &&
      (value as PermissionConfig).type === undefined
    ) {
      if (setNestedPermissionConfig(value as ProviderPermissionConfig, targetSubModule, newConfig)) {
        return true;
      }
    }
  }

  return false;
}

/**
 * Update allPermissions (view/operate) in a nested permission config.
 * Enforces view→operate dependency: operate is disabled when view is false.
 */
export function updateNestedAllPermission(
  config: ProviderPermissionConfig,
  targetSubModule: string,
  permissionType: 'view' | 'operate',
  checked: boolean
): boolean {
  if (
    config[targetSubModule] &&
    typeof config[targetSubModule] === 'object' &&
    (config[targetSubModule] as PermissionConfig).type !== undefined
  ) {
    const subModuleConfig = {
      ...(config[targetSubModule] as PermissionConfig),
      allPermissions: {
        ...(config[targetSubModule] as PermissionConfig).allPermissions
      }
    };

    if (permissionType === 'view') {
      subModuleConfig.allPermissions.view = checked;
      if (!checked) {
        subModuleConfig.allPermissions.operate = false;
      }
    } else if (permissionType === 'operate') {
      if (subModuleConfig.allPermissions.view) {
        subModuleConfig.allPermissions.operate = checked;
      }
    }

    config[targetSubModule] = subModuleConfig;
    return true;
  }

  for (const key in config) {
    const value = config[key];
    if (
      value &&
      typeof value === 'object' &&
      (value as PermissionConfig).type === undefined
    ) {
      if (updateNestedAllPermission(value as ProviderPermissionConfig, targetSubModule, permissionType, checked)) {
        return true;
      }
    }
  }

  return false;
}

/**
 * Update specificData permission in a nested permission config.
 */
export function updateNestedSpecificData(
  config: ProviderPermissionConfig,
  targetSubModule: string,
  record: DataPermission,
  permissionType: 'view' | 'operate'
): boolean {
  if (
    config[targetSubModule] &&
    typeof config[targetSubModule] === 'object' &&
    (config[targetSubModule] as PermissionConfig).type !== undefined
  ) {
    const subConfig = config[targetSubModule] as PermissionConfig;

    if (!subConfig.specificData) {
      subConfig.specificData = [];
    }

    const specificData = [...subConfig.specificData];
    const dataIndex = specificData.findIndex(item => item.id === record.id);

    if (dataIndex === -1) {
      specificData.push({
        id: record.id,
        name: record.name,
        view: record.view,
        operate: record.operate
      });
    } else {
      const item = { ...specificData[dataIndex] };
      if (permissionType === 'view') {
        item.view = record.view;
        if (!record.view) {
          item.operate = false;
        }
      } else if (permissionType === 'operate') {
        if (item.view) {
          item.operate = record.operate;
        }
      }
      specificData[dataIndex] = item;
    }

    config[targetSubModule] = {
      ...subConfig,
      specificData
    };
    return true;
  }

  for (const key in config) {
    const value = config[key];
    if (
      value &&
      typeof value === 'object' &&
      (value as PermissionConfig).type === undefined
    ) {
      if (updateNestedSpecificData(value as ProviderPermissionConfig, targetSubModule, record, permissionType)) {
        return true;
      }
    }
  }

  return false;
}

/**
 * Check if a module permission has sub-modules (is a provider config vs flat module config).
 */
export function hasSubModules(modulePermission: ModulePermissionConfig | ProviderPermissionConfig): boolean {
  return modulePermission && typeof (modulePermission as ModulePermissionConfig).type === 'undefined';
}

// ============================================================
// Permission Conversion Functions (for API <-> Form data)
// ============================================================

/**
 * Convert form permission config to API format (PermissionRuleItem[]).
 * Handles both 'all' and 'specific' permission types.
 */
export function convertPermissionsForApi(
  moduleConfig: PermissionConfig | undefined
): PermissionRuleItem[] {
  const permissionArray: PermissionRuleItem[] = [];

  if (!moduleConfig) return permissionArray;

  if (moduleConfig.type === 'all') {
    const permissions: string[] = [];

    if (moduleConfig.allPermissions?.view) {
      permissions.push('View');

      if (moduleConfig.allPermissions?.operate) {
        permissions.push('Operate');
      }
    }

    if (permissions.length > 0) {
      permissionArray.push({
        id: '0',
        name: 'All',
        permission: permissions
      });
    }
  }

  if (moduleConfig.type === 'specific') {
    if (moduleConfig.specificData && moduleConfig.specificData.length > 0) {
      moduleConfig.specificData.forEach((item: DataPermission) => {
        const permissions: string[] = [];

        if (item.view) {
          permissions.push('View');

          if (item.operate) {
            permissions.push('Operate');
          }
        }

        if (permissions.length > 0) {
          permissionArray.push({
            id: item.id,
            name: item.name,
            permission: permissions
          });
        }
      });
    }

    // When specificData is empty or has no valid permissions, add placeholder
    // to indicate user selected specific type
    if (permissionArray.length === 0) {
      permissionArray.push({
        id: '-1',
        name: 'specific',
        permission: []
      });
    }
  }

  return permissionArray;
}

/**
 * Convert API permission data to form data format (PermissionConfig).
 */
export function convertApiDataToFormData(
  items: PermissionRuleItem[]
): PermissionConfig {
  const hasWildcard = items.some(item => item.id === '0');
  const hasEmptySpecific = items.some(item => item.id === '-1');

  let wildcardItem;
  if (hasWildcard) {
    wildcardItem = items.find(item => item.id === '0');
  }

  const wildcardPermissions = wildcardItem?.permission || [];
  const hasView = wildcardPermissions.includes('View');
  const hasOperate = wildcardPermissions.includes('Operate');

  return {
    type: hasWildcard ? 'all' : 'specific',
    allPermissions: hasWildcard ? {
      view: hasView,
      operate: hasOperate
    } : { view: true, operate: true },
    specificData: hasEmptySpecific ? [] : items
      .filter(item => item.id !== '0')
      .map(item => {
        const hasItemView = item.permission.includes('View');
        const hasItemOperate = item.permission.includes('Operate');
        return {
          id: item.id,
          name: item.name,
          view: hasItemView,
          operate: hasItemOperate
        };
      })
  };
}

/**
 * Recursively convert API data to form data for nested structures.
 */
export function convertApiDataToFormDataRecursive(
  rulesData: Record<string, unknown>
): Record<string, unknown> {
  const result: Record<string, unknown> = {};

  Object.keys(rulesData).forEach(key => {
    const value = rulesData[key];

    if (
      Array.isArray(value) &&
      value.length > 0 &&
      value.every(item =>
        item &&
        typeof item === 'object' &&
        'id' in item &&
        'permission' in item
      )
    ) {
      result[key] = convertApiDataToFormData(value as PermissionRuleItem[]);
    } else if (value && typeof value === 'object' && !Array.isArray(value)) {
      result[key] = convertApiDataToFormDataRecursive(value as Record<string, unknown>);
    }
  });

  return result;
}

/**
 * Create default permission rule structure for modules.
 */
export function createDefaultPermissionRule(
  modules: string[],
  moduleConfigs?: ModuleItem[]
): Record<string, unknown> {
  const defaultPermissionRule: Record<string, unknown> = {};

  modules.forEach(module => {
    const moduleConfig = moduleConfigs?.find(config => config.name === module);

    if (moduleConfig?.children && moduleConfig.children.length > 0) {
      const buildDefaultNestedStructure = (children: ModuleItem[]): Record<string, unknown> => {
        const nestedStructure: Record<string, unknown> = {};

        children.forEach(child => {
          if (!child.children || child.children.length === 0) {
            nestedStructure[child.name] = {
              type: 'specific',
              allPermissions: { view: true, operate: true },
              specificData: []
            };
          } else {
            nestedStructure[child.name] = buildDefaultNestedStructure(child.children);
          }
        });

        return nestedStructure;
      };

      defaultPermissionRule[module] = buildDefaultNestedStructure(moduleConfig.children);
    } else {
      defaultPermissionRule[module] = {
        type: 'specific',
        allPermissions: { view: true, operate: true },
        specificData: []
      };
    }
  });

  return defaultPermissionRule;
}

interface LeafNode {
  path: string[];
  leafName: string;
}

/**
 * Collect all leaf nodes (nodes with 'type' property) from a nested config.
 */
export function collectLeafNodes(
  config: Record<string, unknown>,
  currentPath: string[] = []
): LeafNode[] {
  const leafNodes: LeafNode[] = [];

  if (!config || typeof config !== 'object') {
    return leafNodes;
  }

  for (const key in config) {
    const value = config[key];
    if (value && typeof value === 'object' && value !== null) {
      if (typeof (value as PermissionConfig).type !== 'undefined') {
        const fullPath = [...currentPath, key];
        leafNodes.push({
          path: fullPath,
          leafName: key
        });
      } else {
        const childLeafNodes = collectLeafNodes(value as Record<string, unknown>, [...currentPath, key]);
        leafNodes.push(...childLeafNodes);
      }
    }
  }

  return leafNodes;
}

/**
 * Build nested rules structure from leaf nodes for API submission.
 */
export function buildNestedRules(
  leafNodes: LeafNode[],
  moduleConfig: Record<string, unknown>
): Record<string, unknown> {
  const nestedRules: Record<string, unknown> = {};

  leafNodes.forEach(({ path, leafName }) => {
    let targetConfig: unknown = moduleConfig;
    for (const pathSegment of path) {
      if (targetConfig && typeof targetConfig === 'object') {
        targetConfig = (targetConfig as Record<string, unknown>)[pathSegment];
      }
    }

    if (targetConfig && typeof (targetConfig as PermissionConfig).type !== 'undefined') {
      const permissionArray = convertPermissionsForApi(targetConfig as PermissionConfig);

      if (permissionArray.length > 0) {
        if (path.length === 1) {
          nestedRules[leafName] = permissionArray;
        } else {
          let currentLevel = nestedRules;

          for (let i = 0; i < path.length - 1; i++) {
            const pathSegment = path[i];
            if (!currentLevel[pathSegment]) {
              currentLevel[pathSegment] = {};
            }
            currentLevel = currentLevel[pathSegment] as Record<string, unknown>;
          }

          currentLevel[leafName] = permissionArray;
        }
      }
    }
  });

  return nestedRules;
}

/**
 * Transform permission rules from form data to API format.
 * Handles both flat and nested module structures.
 */
export function transformPermissionRulesForApi(
  permissionRule: Record<string, unknown>,
  supportedModules: string[]
): Record<string, unknown> {
  const transformedRules: Record<string, unknown> = {};

  supportedModules.forEach(moduleKey => {
    const moduleConfig = permissionRule[moduleKey];
    if (!moduleConfig) return;

    const isReallyFlatStructure = typeof (moduleConfig as PermissionConfig).type !== 'undefined';

    if (!isReallyFlatStructure) {
      const leafNodes = collectLeafNodes(moduleConfig as Record<string, unknown>);
      const moduleRules = buildNestedRules(leafNodes, moduleConfig as Record<string, unknown>);

      if (Object.keys(moduleRules).length > 0) {
        transformedRules[moduleKey] = moduleRules;
      }
    } else {
      const permissionArray = convertPermissionsForApi(moduleConfig as PermissionConfig);

      if (permissionArray.length > 0) {
        transformedRules[moduleKey] = permissionArray;
      }
    }
  });

  return transformedRules;
}
