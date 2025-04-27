import React from 'react';
import OneLineEllipsisWithTooltip from '@/components/ellipsis-with-tooltip';

interface OneLineEllipsisIntroProps {
  name: string | null;
  desc: string | null;
}

const OneLineEllipsisIntro: React.FC<OneLineEllipsisIntroProps> = ({ name, desc }) => {
  return (
    <div className="w-full h-full flex items-center">
      <div className="flex-1 overflow-hidden">
        <OneLineEllipsisWithTooltip
          text={name}
          className="text-base font-semibold mb-2 whitespace-nowrap overflow-hidden text-ellipsis"
        />
        <OneLineEllipsisWithTooltip
          text={desc}
          className="text-xs whitespace-nowrap overflow-hidden text-ellipsis text-[var(--color-text-3)]"
        />
      </div>
    </div>
  );
};

export default OneLineEllipsisIntro;
