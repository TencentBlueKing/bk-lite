import React from 'react';
import { WC } from '../chrome';

const bars = [
  { side: 'user' as const, widths: ['42%'] },
  { side: 'bot' as const, widths: ['78%', '92%', '64%'] },
  { side: 'user' as const, widths: ['36%'] },
  { side: 'bot' as const, widths: ['88%', '70%'] },
];

function Bone({ width }: { width: string }) {
  return (
    <div
      className="h-3 animate-pulse rounded-full"
      style={{ width, background: WC.botBorder }}
    />
  );
}

export function ConversationSkeleton() {
  return (
    <div className="flex flex-col gap-4" aria-busy="true" aria-label="加载对话">
      {bars.map((row, index) => {
        const isBot = row.side === 'bot';
        return (
          <div
            key={index}
            className={`flex w-full items-start gap-2 ${isBot ? 'justify-start' : 'flex-row-reverse justify-start'}`}
          >
            <div
              className="h-8 w-8 flex-shrink-0 animate-pulse rounded-full"
              style={{ background: isBot ? WC.indigoHi : WC.success, opacity: 0.35 }}
            />
            <div
              className={`flex flex-col gap-2 px-3.5 py-3 ${isBot ? 'min-w-0 flex-1' : 'w-[42%]'}`}
              style={{
                background: isBot ? WC.botBubble : WC.primaryBg,
                borderRadius: 18,
                borderBottomLeftRadius: isBot ? 6 : 18,
                borderBottomRightRadius: isBot ? 18 : 6,
              }}
            >
              {row.widths.map((width) => (
                <Bone key={width} width={width} />
              ))}
            </div>
          </div>
        );
      })}
    </div>
  );
}
