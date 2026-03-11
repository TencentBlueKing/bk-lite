/**
 * Introduction JSON Configuration Types
 * Used for rendering plugin introduction pages with Ant Design components
 */

// Feature item displayed in feature grid
export interface IntroFeatureItem {
  icon: string; // Emoji or icon identifier
  title: string;
  description: string;
}

// Features section with title and items
export interface IntroFeatures {
  title: string;
  items: IntroFeatureItem[];
}

// Table column definition
export interface IntroTableColumn {
  key: string;
  title: string;
  width?: number | string;
}

// Field table section (for parsed fields, event IDs, etc.)
export interface IntroFieldTable {
  title: string;
  description?: string;
  columns: IntroTableColumn[];
  data: Record<string, string>[];
}

// Tip/Alert item (warning, info, code block)
export interface IntroTip {
  type: 'warning' | 'info' | 'success' | 'error';
  title?: string;
  content: string; // Supports simple markdown: **bold**, `code`, \n for newlines
}

// Code block section
export interface IntroCodeBlock {
  title?: string;
  language?: string;
  code: string;
}

// Best practices section with list items
export interface IntroBestPractices {
  title: string;
  items: string[]; // Each item supports simple markdown
}

// Step item for step-by-step guides
export interface IntroStepItem {
  title: string;
  description: string;
  code?: string;
}

// Steps section
export interface IntroSteps {
  title: string;
  description?: string; // Optional description below the title
  items: IntroStepItem[];
}

// Main introduction configuration
export interface IntroConfig {
  // Overview section - paragraphs of description
  overview: {
    title: string;
    paragraphs: string[];
  };

  // Features section - grid of feature cards
  features?: IntroFeatures;

  // Field tables - one or more tables showing parsed fields
  fieldTables?: IntroFieldTable[];

  // Tips/Alerts - warning messages, configuration tips
  tips?: IntroTip[];

  // Code blocks - configuration examples
  codeBlocks?: IntroCodeBlock[];

  // Best practices - list of recommendations
  bestPractices?: IntroBestPractices;

  // Steps - step-by-step guide
  steps?: IntroSteps;
}

// Theme color for different plugin types
export type IntroThemeColor =
  | 'blue' // Default - #0052d9
  | 'green' // Syslog, Docker - #43a047
  | 'red' // Apache - #D22128
  | 'orange' // SNMP, Kafka - #ff9800
  | 'cyan' // Windows - #00A4EF
  | 'purple' // Elasticsearch - #f0b90b
  | 'pink' // Redis - #dc382d
  | 'yellow' // MySQL - #4479a1
  | 'teal'; // MongoDB - #00684a

// Extended config with theme
export interface IntroConfigWithTheme extends IntroConfig {
  themeColor?: IntroThemeColor;
}
