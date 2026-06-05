'use client';

import React, { useEffect, useState } from 'react';
import { message, Tag } from 'antd';
import type { DataNode as TreeDataNode } from 'antd/lib/tree';
import { useSecurityApi } from '@/app/system-manager/api/security';
import { useUserApi } from '@/app/system-manager/api/user/index';
import AuthSourcesList from '@/app/system-manager/components/security/sourcesList';
import type { AuthSource } from '@/app/system-manager/types/security';
import { enhanceAuthSourcesList } from '@/app/system-manager/utils/authSourceUtils';
import { useClientData } from '@/context/client';
import { useTranslation } from '@/utils/i18n';

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
          title: item.is_build_in === false
            ? <span>{item.name}<Tag color="green" className="ml-1" style={{ fontSize: 11, padding: '0 4px' }}>{t('common.externalApp')}</Tag></span>
            : item.name,
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
