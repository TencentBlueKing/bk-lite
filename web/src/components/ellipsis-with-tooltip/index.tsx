import React, { useRef, useEffect, useState } from 'react';
import { Tooltip } from 'antd';

const OVERFLOW_MEASUREMENT_TOLERANCE = 1;

export interface EllipsisWithTooltipProps {
  text: React.ReactNode;
  className?: string;
  /**
   * `hover` 保持原有行为；`interactive` 让实际溢出的文本也可通过
   * 键盘聚焦和点击查看完整内容。
   */
  disclosure?: 'hover' | 'interactive';
}

const EllipsisWithTooltip: React.FC<EllipsisWithTooltipProps> = ({
  text,
  className = '',
  disclosure = 'hover',
}) => {
  const textRef = useRef<HTMLDivElement>(null);
  const [isOverflow, setIsOverflow] = useState(false);

  const checkOverflow = (element: HTMLDivElement | null, setOverflow: (value: boolean) => void) => {
    if (element) {
      // DOM 的 client/scroll 尺寸是整数；小数行高可能分别向下、向上取整，
      // 产生 1px 的假溢出。只把超过取整误差的差值视为真实溢出。
      setOverflow(
        element.scrollWidth - element.clientWidth > OVERFLOW_MEASUREMENT_TOLERANCE ||
          element.scrollHeight - element.clientHeight > OVERFLOW_MEASUREMENT_TOLERANCE
      );
    }
  };

  useEffect(() => {
    // requestAnimationFrame will execute the callback function before the browser's next repaint, ensuring the check is performed after the element is rendered
    const frameId = requestAnimationFrame(() => {
      checkOverflow(textRef.current, setIsOverflow);
    });

    const handleResize = () => {
      cancelAnimationFrame(frameId);
      requestAnimationFrame(() => {
        checkOverflow(textRef.current, setIsOverflow);
      });
    };

    window.addEventListener('resize', handleResize);

    return () => {
      cancelAnimationFrame(frameId);
      window.removeEventListener('resize', handleResize);
    };
  }, [text]);

  return (
    <>
      {isOverflow ? (
        <Tooltip
          title={text}
          // 可聚焦元素在鼠标点击时会触发 focus；不再叠加 click trigger，
          // 避免同一次点击先打开又被 click toggle 关闭。
          trigger={disclosure === 'interactive' ? ['hover', 'focus'] : 'hover'}
        >
          <div
            ref={textRef}
            className={className}
            tabIndex={disclosure === 'interactive' ? 0 : undefined}
            aria-label={
              disclosure === 'interactive' && (typeof text === 'string' || typeof text === 'number')
                ? String(text)
                : undefined
            }
          >
            {text}
          </div>
        </Tooltip>
      ) : (
        <div ref={textRef} className={className}>
          {text}
        </div>
      )}
    </>
  );
};

export default EllipsisWithTooltip;
