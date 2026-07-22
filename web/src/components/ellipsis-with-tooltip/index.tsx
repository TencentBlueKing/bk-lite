import React, { useRef, useEffect, useState } from 'react';
import { Tooltip } from 'antd';

interface EllipsisWithTooltipProps {
  text: React.ReactNode;
  className?: string;
}

const EllipsisWithTooltip: React.FC<EllipsisWithTooltipProps> = ({ text, className = '' }) => {
  const textRef = useRef<HTMLDivElement>(null);
  const [isOverflow, setIsOverflow] = useState(false);

  const checkOverflow = (element: HTMLDivElement | null, setOverflow: (value: boolean) => void) => {
    if (element) {
      setOverflow(
        element.scrollWidth > element.clientWidth ||
          element.scrollHeight > element.clientHeight
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
