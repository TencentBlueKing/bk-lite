'use client';

import { useSearchParams } from 'next/navigation';
import IpamMatrix from './ipamMatrix';

const IpViewPage = () => {
  const searchParams = useSearchParams();
  const instUuid = searchParams.get('inst_uuid') || '';
  return <IpamMatrix instUuid={instUuid} />;
};

export default IpViewPage;
