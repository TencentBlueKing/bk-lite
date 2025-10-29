interface SearchValue {
  field: string;
  value: string;
}

interface SearchCombinationProps {
  defaultValue?: SearchValue;
  onChange?: (value: SearchValue) => void;
  className?: string;
}

export type { SearchValue, SearchCombinationProps };
