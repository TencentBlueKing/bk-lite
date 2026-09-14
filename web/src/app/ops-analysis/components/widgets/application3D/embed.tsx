'use client';

import React from 'react';
import Application3D from '@/app/ops-analysis/components/widgets/application3D';

export interface Application3DEmbedProps {
  instUuid: string;
}

const Application3DEmbed = ({ instUuid }: Application3DEmbedProps) => {
  return (
    <div className="h-full min-h-[280px] min-w-0">
      <Application3D
        instUuid={instUuid}
        surface="screen"
        runtimeActive
      />
    </div>
  );
};

export default Application3DEmbed;
