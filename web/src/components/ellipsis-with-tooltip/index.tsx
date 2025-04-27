import React, { useRef, useEffect, useState } from 'react';
import { Tooltip } from 'antd';

interface EllipsisWithTooltipProps {
  text: string | null;
  className?: string;
}

const EllipsisWithTooltip: React.FC<EllipsisWithTooltipProps> = ({ text, className = '' }) => {
  const textRef = useRef<HTMLDivElement>(null);
  const [isOverflow, setIsOverflow] = useState(false);

  const checkOverflow = (element: HTMLDivElement | null, setOverflow: (value: boolean) => void) => {
    if (element) {
      setOverflow(element.scrollWidth > element.clientWidth);
    }
  };

  useEffect(() => {
    // requestAnimationFrame 会在浏览器下次重绘之前执行回调函数，确保在元素渲染完成后再进行检查
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
        <Tooltip title={text}>
          <div ref={textRef} className={className}>
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
