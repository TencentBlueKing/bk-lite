import React from 'react';

interface DetailLayoutProps {
  children: React.ReactNode;
}

export default function DetailLayout({ children }: DetailLayoutProps) {
  return <>{children}</>;
}
