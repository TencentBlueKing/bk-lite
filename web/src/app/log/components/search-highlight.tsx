'use client';

import React from 'react';
import { splitHighlightedText } from '@/app/log/utils/searchHighlight';

interface SearchHighlightProps {
  text?: unknown;
  terms: string[];
  empty?: React.ReactNode;
}

const SearchHighlight: React.FC<SearchHighlightProps> = ({
  text,
  terms,
  empty = '--'
}) => {
  if (text == null || text === '') {
    return <>{empty}</>;
  }
  const value = String(text);
  const parts = splitHighlightedText(value, terms);
  return (
    <>
      {parts.map((part, index) =>
        part.match ? (
          <mark
            key={index}
            className="rounded-sm bg-[var(--color-warning)]/30 p-0 not-italic text-inherit"
          >
            {part.text}
          </mark>
        ) : (
          <React.Fragment key={index}>{part.text}</React.Fragment>
        )
      )}
    </>
  );
};

export default SearchHighlight;
