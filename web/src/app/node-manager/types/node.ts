import React from 'react';

// Re-export shared search types from framework component
export type { SearchFilters, FieldConfig, SearchCombinationProps } from '@/components/search-combination/types';

interface SearchValue {
  field: string;
  value: string;
}

interface SearchTag {
  type: 'string' | 'enum';
  field: string;
  value: string;
  options?: Array<{ id: string; name: string }>;
}

interface NodeParams {
  id?: React.Key;
  name?: string;
  organization?: Array<React.Key>;
  organizations?: Array<React.Key>;
}

export type {
  SearchValue,
  SearchTag,
  NodeParams,
};