'use client';

import { useSearchParams } from 'next/navigation';
import K8sResourceDetailsContent, {
  K8sOverviewContent,
} from './K8sResourceDetailsContent';

export { K8sOverviewContent };

/**
 * Detail-route entry: read cluster id from searchParams and render shared content.
 * Views hub embeds `K8sResourceDetailsContent` directly with focus.inst_id.
 */
const K8sResourceDetails = () => {
  const searchParams = useSearchParams();
  const instId = searchParams.get('inst_id') || '';
  return <K8sResourceDetailsContent instId={instId} />;
};

export default K8sResourceDetails;
