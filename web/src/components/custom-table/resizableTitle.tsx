import React, { useCallback, useRef } from 'react';

interface ResizableTitleProps extends React.ThHTMLAttributes<HTMLTableCellElement> {
  resizeHandler?: (width: number) => void;
  width?: number;
}

const ResizableTitle: React.FC<ResizableTitleProps> = ({ resizeHandler, width, ...restProps }) => {
  const thRef = useRef<HTMLTableCellElement>(null);

  const handleMouseDown = useCallback(
    (e: React.MouseEvent) => {
      if (!resizeHandler || !width) return;
      e.preventDefault();
      e.stopPropagation();

      const startX = e.clientX;
      const startWidth = width;

      const onMouseMove = (moveEvent: MouseEvent) => {
        const newWidth = Math.max(startWidth + moveEvent.clientX - startX, 50);
        resizeHandler(newWidth);
      };

      const onMouseUp = () => {
        document.removeEventListener('mousemove', onMouseMove);
        document.removeEventListener('mouseup', onMouseUp);
        document.body.style.cursor = '';
        document.body.style.userSelect = '';
      };

      document.addEventListener('mousemove', onMouseMove);
      document.addEventListener('mouseup', onMouseUp);
      document.body.style.cursor = 'col-resize';
      document.body.style.userSelect = 'none';
    },
    [resizeHandler, width]
  );

  if (!width || !resizeHandler) {
    return <th {...restProps} />;
  }

  return (
    <th {...restProps} ref={thRef}>
      {restProps.children}
      <span
        className="react-resizable-handle"
        onMouseDown={handleMouseDown}
        onClick={(e) => e.stopPropagation()}
      />
    </th>
  );
};

export default ResizableTitle;
