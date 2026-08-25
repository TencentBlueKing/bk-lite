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
    <div className="flex flex-col gap-5" aria-busy="true" aria-label="加载对话">
      {bars.map((row, index) => {
        const isBot = row.side === 'bot';
        return (
          <div
            key={index}
            className={`flex w-full items-start ${isBot ? 'justify-start' : 'flex-row-reverse justify-start'}`}
          >
            {isBot ? (
              <div className="flex min-w-0 flex-1 flex-col gap-2">
                {row.widths.map((width) => (
                  <Bone key={width} width={width} />
                ))}
              </div>
            ) : (
              <div
                className="flex w-[42%] flex-col gap-2 px-3.5 py-2"
                style={{
                  background: WC.botBubble,
                  borderRadius: 16,
                  borderBottomRightRadius: 4,
                }}
              >
                {row.widths.map((width) => (
                  <Bone key={width} width={width} />
                ))}
              </div>
            )}
          </div>
        );
      })}
    </div>
  );
}
