'use client';

import React from 'react';

export default function ItsmLayout({ children }: { children: React.ReactNode }) {
  return <div className="p-4">{children}</div>;
}
