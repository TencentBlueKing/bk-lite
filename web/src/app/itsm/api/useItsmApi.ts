'use client';

import useApiClient from '@/utils/request';

export function useItsmApi() {
  const { get, post, put, del } = useApiClient();
  return {
    listForms: () => get('/itsm/api/forms/'),
    publishForm: (id: number, schema: unknown) => post(`/itsm/api/forms/${id}/publish/`, { schema }),
    listWorkflows: () => get('/itsm/api/workflows/'),
    saveDesign: (id: number, design: unknown) => put(`/itsm/api/workflows/${id}/design/`, design),
    publishWorkflow: (id: number) => post(`/itsm/api/workflows/${id}/publish/`),
    listTickets: () => get('/itsm/api/tickets/'),
    remove: (path: string) => del(path),
  };
}
