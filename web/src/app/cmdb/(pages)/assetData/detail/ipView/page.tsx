'use client';

import { useSearchParams } from 'next/navigation';
import IpamMatrix from './ipamMatrix';

const IpViewPage = () => {
  const searchParams = useSearchParams();
  const instId = searchParams.get('inst_id') || '';
  return <IpamMatrix instId={instId} />;
};

export default IpViewPage;
