'use client';

import React, { useState, useEffect } from 'react';
import { message } from 'antd';
import { useTranslation } from '@/utils/i18n';
import { useSecurityApi } from '@/app/system-manager/api/security';
import { AuthSource } from '@/app/system-manager/types/security';
import { enhanceAuthSourcesList } from '@/app/system-manager/utils/authSourceUtils';
import type { DataNode as TreeDataNode } from 'antd/lib/tree';
import { useUserApi } from '@/app/system-manager/api/user/index';
import { useClientData } from '@/context/client';
import AuthSourcesList from '@/app/system-manager/components/security/sourcesList';

const AuthSourcesPage: React.FC = () => {
  const { t } = useTranslation();
  const [authSourcesLoading, setAuthSourcesLoading] = useState(false);
  const [authSources, setAuthSources] = useState<AuthSource[]>([]);
  const { getAuthSources } = useSecurityApi();
  const { clientData } = useClientData();
  const { getRoleList } = useUserApi();
  const [roleTreeData, setRoleTreeData] = useState<TreeDataNode[]>([]);

  useEffect(() => {
    fetchAuthSources();
    fetchRoleInfo();
  }, []);

  const fetchAuthSources = async () => {
    try {
      setAuthSourcesLoading(true);
      const data = await getAuthSources();
      const enhancedData = enhanceAuthSourcesList(data || []);
      setAuthSources(enhancedData);
    } catch (error) {
      console.error('Failed to fetch auth sources:', error);
      setAuthSources([]);
    } finally {
      setAuthSourcesLoading(false);
    }
  };

  const fetchRoleInfo = async () => {
    try {
      const roleData = await getRoleList({ client_list: clientData });
      setRoleTreeData(
        roleData.map((item: any) => ({
          key: item.id,
          title: item.name,
          selectable: false,
          children: item.children.map((child: any) => ({
            key: child.id,
            title: child.name,
            selectable: true,
          })),
        }))
      );
    } catch {
      message.error(t('common.fetchFailed'));
    }
  };

  return (
    <AuthSourcesList
      authSources={authSources}
      loading={authSourcesLoading}
      roleTreeData={roleTreeData}
      onUpdate={setAuthSources}
    />
  );
};

export default AuthSourcesPage;
