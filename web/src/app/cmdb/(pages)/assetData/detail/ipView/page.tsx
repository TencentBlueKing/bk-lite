'use client';

import { useSearchParams } from 'next/navigation';
import IpamMatrix from './ipamMatrix';

const IpViewPage = () => {
  const searchParams = useSearchParams();
  const instUuid = searchParams.get('inst_uuid') || '';
  return (
    <div className="h-full min-h-0 min-w-0 overflow-auto">
      <IpamMatrix instUuid={instUuid} />
    </div>
  );
};

export default IpViewPage;
