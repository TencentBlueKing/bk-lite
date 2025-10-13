'use client';
import React, { useState } from 'react';
import { Popover } from 'antd';

interface CustomPopoverProps {
  title?: string;
  children: React.ReactNode;
  content?: React.ReactNode | ((onClose: () => void) => React.ReactNode);
}

const CustomPopover: React.FC<CustomPopoverProps> = ({
  title,
  children,
  content,
}) => {
  const [open, setOpen] = useState(false);

  const handleOpenChange = (newOpen: boolean) => {
    setOpen(newOpen);
  };

  const handleClose = () => {
    setOpen(false);
  };

  const renderContent = () => {
    if (typeof content === 'function') {
      return content(handleClose);
    }
    if (React.isValidElement(content)) {
      return React.cloneElement(content as React.ReactElement<any>, {
        onClose: handleClose,
      });
    }
    return content;
  };

  return (
    <Popover
      overlayClassName="custom-popover"
      title={title}
      arrow={false}
      trigger="click"
      getPopupContainer={(trigger) => document.body || trigger.parentElement}
      content={renderContent()}
      open={open}
      onOpenChange={handleOpenChange}
    >
      {children}
    </Popover>
  );
};

export default CustomPopover;
