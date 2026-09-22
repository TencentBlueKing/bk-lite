import { useMemo } from 'react';
import { useSession } from 'next-auth/react';
import { useAuth } from '@/context/auth';
import useApiClient from '@/utils/request';
import type { TransferExportRequest, TransferList, TransferTask } from '@/app/cmdb/types/transfer';

const base = '/cmdb/api/transfer_tasks/';
export function useTransferApi() {
  const { get, post, del, isLoading } = useApiClient();
  const { data: session } = useSession();
  const auth = useAuth();
  const identity = auth?.token || session?.user?.name || '';
  return useMemo(() => ({
    identity,
    isLoading,
    list: () => get<TransferList>(base, { suppressErrorNotification: true }),
    exportFile: (data: TransferExportRequest, key: string) => post<TransferTask>(`${base}export/`, data, {
      headers: { 'Idempotency-Key': key },
    }),
    importFile: (model: string, file: File, key: string, progress: (percent: number) => void) => {
      const form = new FormData();
      form.append('model_id', model);
      form.append('file', file);
      return post<TransferTask>(`${base}import/`, form, {
        headers: { 'Content-Type': 'multipart/form-data', 'Idempotency-Key': key },
        timeout: 300000,
        onUploadProgress: (event) => { if (event.total) progress(Math.round(event.loaded * 100 / event.total)); },
      });
    },
    retry: (id: string, key: string) => post<TransferTask>(`${base}${id}/retry/`, {}, { headers: { 'Idempotency-Key': key } }),
    cancel: (id: string) => post(`${base}${id}/cancel/`),
    remove: (id: string) => del(`${base}${id}/`),
    download: (id: string, artifact: 'result' | 'errors') => post<Blob>(`${base}${id}/download/`, { artifact }, {
      responseType: 'blob', timeout: 300000,
    }),
  }), [get, post, del, identity, isLoading]);
}
