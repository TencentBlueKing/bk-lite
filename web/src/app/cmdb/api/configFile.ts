import { useCallback, useMemo } from 'react';
import useApiClient from '@/utils/request';
import type { CreateManualConfigFileParams } from '@/app/cmdb/types/configFile';

export const useConfigFileApi = () => {
  const { get, del, post } = useApiClient();

  const getConfigFileList = useCallback(
    (instance_id: string) =>
      get('/cmdb/api/config_file_versions/file_list/', { params: { instance_id } }),
    [get]
  );

  const getConfigFileVersions = useCallback(
    (instance_id: string, file_path: string) =>
      get('/cmdb/api/config_file_versions/', { params: { instance_id, file_path, page_size: -1 } }),
    [get]
  );

  const getConfigFileContent = useCallback(
    (versionId: number, encoding = 'utf-8') =>
      get(`/cmdb/api/config_file_versions/${versionId}/content/`, { params: { encoding } }),
    [get]
  );

  const deleteConfigFileVersion = useCallback(
    (versionId: number) => del(`/cmdb/api/config_file_versions/${versionId}/`),
    [del]
  );

  const getConfigFileDiff = useCallback(
    (version_id_1: number, version_id_2: number) =>
      get('/cmdb/api/config_file_versions/diff/', {
        params: { version_id_1, version_id_2 },
      }),
    [get]
  );

  const createManualConfigFile = useCallback(
    (params: CreateManualConfigFileParams) =>
      post('/cmdb/api/config_file_versions/create_manual/', params),
    [post]
  );

  return useMemo(
    () => ({
      getConfigFileList,
      getConfigFileVersions,
      getConfigFileContent,
      getConfigFileDiff,
      deleteConfigFileVersion,
      createManualConfigFile,
    }),
    [createManualConfigFile, deleteConfigFileVersion, getConfigFileContent, getConfigFileDiff, getConfigFileList, getConfigFileVersions]
  );
};
