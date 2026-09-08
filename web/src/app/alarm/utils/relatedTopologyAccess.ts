import { HandledRequestError } from '@/utils/request';

export const RELATED_TOPOLOGY_API_PATH =
  '/operation_analysis/api/scene_widgets/related_topology/';

type PostFn = (
  url: string,
  body: unknown,
  options?: { suppressErrorNotification?: boolean },
) => Promise<unknown>;

export type RelatedTopologyAccess = 'ok' | 'hidden' | 'retryable';

export async function probeRelatedTopologyAccess(
  post: PostFn,
  instUuid: string,
): Promise<RelatedTopologyAccess> {
  try {
    await post(
      RELATED_TOPOLOGY_API_PATH,
      { inst_uuid: instUuid },
      { suppressErrorNotification: true },
    );
    return 'ok';
  } catch (error) {
    const status = error instanceof HandledRequestError ? error.status : undefined;
    if (status === 403 || status === 404) {
      return 'hidden';
    }
    return 'retryable';
  }
}
