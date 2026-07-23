import type {
  CreateIncidentIMGroupParams,
  IncidentIMGroup,
  IncidentIMGroupOptions,
  IncidentIMMemberList,
  IncidentIMMemberListParams,
  UpdateIncidentIMGroupParams,
} from '@/app/alarm/types/incidents';

export interface IncidentIMGroupRequestConfig {
  params?: object;
  data?: unknown;
  signal?: AbortSignal;
}

export interface IncidentIMGroupHttpClient {
  get: <T>(url: string, config?: IncidentIMGroupRequestConfig) => Promise<T>;
  post: <T>(url: string, data?: unknown, config?: IncidentIMGroupRequestConfig) => Promise<T>;
  patch: <T>(url: string, data?: unknown, config?: IncidentIMGroupRequestConfig) => Promise<T>;
  del: <T>(url: string, config?: IncidentIMGroupRequestConfig) => Promise<T>;
}

export const createIncidentIMGroupApi = ({
  get,
  post,
  patch,
  del,
}: IncidentIMGroupHttpClient) => {
  const groupPath = (incidentPk: string) => `/alerts/api/incident/${incidentPk}/im-group/`;

  const getIncidentIMGroup = async (
    incidentPk: string,
    signal?: AbortSignal,
  ): Promise<IncidentIMGroup | null> => {
    return get<IncidentIMGroup | null>(groupPath(incidentPk), { signal });
  };

  const getIncidentIMGroupOptions = async (
    incidentPk: string,
    channelId?: number,
    signal?: AbortSignal,
  ): Promise<IncidentIMGroupOptions> => {
    return get<IncidentIMGroupOptions>(`${groupPath(incidentPk)}options/`, {
      params: channelId === undefined ? undefined : { channel_id: channelId },
      signal,
    });
  };

  const createIncidentIMGroup = async (
    incidentPk: string,
    data: CreateIncidentIMGroupParams,
  ): Promise<IncidentIMGroup> => {
    return post<IncidentIMGroup>(groupPath(incidentPk), data);
  };

  const updateIncidentIMGroup = async (
    incidentPk: string,
    data: UpdateIncidentIMGroupParams,
  ): Promise<IncidentIMGroup> => {
    return patch<IncidentIMGroup>(groupPath(incidentPk), data);
  };

  const getIncidentIMMembers = async (
    incidentPk: string,
    params: IncidentIMMemberListParams,
    signal?: AbortSignal,
  ): Promise<IncidentIMMemberList> => {
    return get<IncidentIMMemberList>(`${groupPath(incidentPk)}members/`, { params, signal });
  };

  const retryIncidentIMGroup = async (incidentPk: string): Promise<IncidentIMGroup> => {
    return post<IncidentIMGroup>(`${groupPath(incidentPk)}retry/`);
  };

  const pauseIncidentIMGroup = async (incidentPk: string): Promise<IncidentIMGroup> => {
    return post<IncidentIMGroup>(`${groupPath(incidentPk)}pause/`);
  };

  const resumeIncidentIMGroup = async (incidentPk: string): Promise<IncidentIMGroup> => {
    return post<IncidentIMGroup>(`${groupPath(incidentPk)}resume/`);
  };

  const unlinkIncidentIMGroup = async (
    incidentPk: string,
    groupName: string,
  ): Promise<void> => {
    return del<void>(groupPath(incidentPk), {
      data: { group_name: groupName },
    });
  };

  return {
    getIncidentIMGroup,
    getIncidentIMGroupOptions,
    createIncidentIMGroup,
    updateIncidentIMGroup,
    getIncidentIMMembers,
    retryIncidentIMGroup,
    pauseIncidentIMGroup,
    resumeIncidentIMGroup,
    unlinkIncidentIMGroup,
  };
};
