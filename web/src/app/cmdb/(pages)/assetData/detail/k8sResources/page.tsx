'use client';

import { useSearchParams } from 'next/navigation';
import K8sResourceDetailsContent, {
  K8sOverviewContent,
} from './K8sResourceDetailsContent';

export { K8sOverviewContent };

/**
 * Detail-route entry: read cluster UUID from searchParams and render shared content.
 * Views hub embeds `K8sResourceDetailsContent` directly with focus.inst_uuid.
 */
const K8sResourceDetails = () => {
  const searchParams = useSearchParams();
  const instUuid = searchParams.get('inst_uuid') || '';
  return (
    <div className="h-full min-h-0 min-w-0 overflow-hidden">
      <K8sResourceDetailsContent instUuid={instUuid} />
    </div>
  );
};

export default K8sResourceDetails;
