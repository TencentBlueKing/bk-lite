import React, { useMemo } from 'react';
import { useTranslation } from '@/utils/i18n';
import PermissionWrapper from '@/components/permission';
import type { MenuProps } from 'antd';
import { ListItem } from '@/types';

const useAssetMenuItems = (): MenuProps['items'] => {
  const { t } = useTranslation();
  return useMemo(
    () => [
      {
        label: (
          <PermissionWrapper
            className="customMenuItem"
            requiredPermissions={['Edit']}
          >
            {t('common.batchEdit')}
          </PermissionWrapper>
        ),
        key: 'batchEdit',
      },
      {
        label: (
          <PermissionWrapper
            className="customMenuItem"
            requiredPermissions={['Delete']}
          >
            {t('common.batchDelete')}
          </PermissionWrapper>
        ),
        key: 'batchDelete',
      },
    ],
    [t]
  );
};

const useConditionList = (): ListItem[] => {
  const { t } = useTranslation();
  return useMemo(
    () => [
      { id: '==', name: '=' },
      { id: '!=', name: '!=' },
      { id: 'contains', name: t('log.include') },
      { id: '!contains', name: t('log.exclude') },
    ],
    [t]
  );
};

const useTermList = (): ListItem[] => {
  const { t } = useTranslation();
  return useMemo(
    () => [
      { id: 'OR', value: 'or', name: t('log.integration.anyCondition') },
      { id: 'AND', value: 'and', name: t('log.integration.allConditions') },
    ],
    [t]
  );
};

const useConditionModeList = (): ListItem[] => {
  const { t } = useTranslation();
  return useMemo(
    () => [
      {
        value: 'continue_past',
        title: 'continue_past',
        label: t('log.integration.continuePast'),
      },
      {
        value: 'continue_through',
        title: 'continue_through',
        label: t('log.integration.continueThrough'),
      },
      {
        value: 'halt_before',
        title: 'halt_before',
        label: t('log.integration.haltBefore'),
      },
      {
        value: 'halt_with',
        title: 'halt_with',
        label: t('log.integration.haltWith'),
      },
    ],
    [t]
  );
};

const useDirectionList = (): ListItem[] => {
  const { t } = useTranslation();
  return useMemo(
    () => [
      { id: 'before', name: t('log.integration.before') },
      { id: 'after', name: t('log.integration.after') },
    ],
    [t]
  );
};

const useRuleCategories = (): ListItem[] => {
  const { t } = useTranslation();
  return useMemo(
    () => [
      {
        id: 'security',
        name: t('log.integration.security'),
        label: t('log.integration.securityDes'),
      },
      {
        id: 'system',
        name: t('log.integration.system'),
        label: t('log.integration.systemDes'),
      },
      {
        id: 'network',
        name: t('log.integration.network'),
        label: t('log.integration.networkDes'),
      },
    ],
    [t]
  );
};

export {
  useAssetMenuItems,
  useConditionList,
  useTermList,
  useConditionModeList,
  useDirectionList,
  useRuleCategories,
};
