'use client';

import React from 'react';
import { OpenApiTokensPageShell } from '@/app/system-manager/components/openapi-tokens';
import { useOpenApiTokensPage } from '@/app/system-manager/hooks/useOpenApiTokensPage';

const SecretKeyPage: React.FC = () => {
  const {
    canViewSystem,
    canManagePersonal,
    canManageSystem,
    personalRows,
    systemRows,
    personalLoading,
    systemLoading,
    scopeCatalog,
    handleCreate,
    handleEdit,
    handleRevokePersonal,
    handleRevokeSystem,
  } = useOpenApiTokensPage();

  return (
    <div className="flex h-full min-h-0 flex-col overflow-hidden">
      <OpenApiTokensPageShell
        canViewSystem={canViewSystem}
        canManagePersonal={canManagePersonal}
        canManageSystem={canManageSystem}
        personalRows={personalRows}
        systemRows={systemRows}
        personalLoading={personalLoading}
        systemLoading={systemLoading}
        scopeCatalog={scopeCatalog}
        onCreate={handleCreate}
        onEdit={handleEdit}
        onRevokePersonal={handleRevokePersonal}
        onRevokeSystem={handleRevokeSystem}
      />
    </div>
  );
};

export default SecretKeyPage;
