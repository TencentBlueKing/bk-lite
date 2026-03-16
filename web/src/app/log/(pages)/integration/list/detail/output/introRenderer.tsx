'use client';

import React, { useEffect, useState } from 'react';
import { Spin, Typography, Alert, message, Table } from 'antd';
import type { ColumnsType } from 'antd/es/table';
import type {
  IntroConfig,
  IntroFeatureItem,
  IntroFieldTable,
  IntroTip,
  IntroCodeBlock
} from '@/app/log/types/introduction';

const { Title, Paragraph, Text } = Typography;

interface IntroRendererProps {
  filePath?: string;
  fileName?: string;
  config?: IntroConfig;
}

// Parse simple markdown-like syntax in text
const parseSimpleMarkdown = (text: string): React.ReactNode => {
  // Split by code blocks first
  const parts = text.split(/(`[^`]+`)/g);

  return parts.map((part, index) => {
    if (part.startsWith('`') && part.endsWith('`')) {
      // Code inline
      return (
        <code
          key={index}
          className="bg-[var(--color-fill-1)] px-1.5 py-0.5 rounded font-mono text-xs"
        >
          {part.slice(1, -1)}
        </code>
      );
    }

    // Handle bold text
    const boldParts = part.split(/(\*\*[^*]+\*\*)/g);
    return boldParts.map((boldPart, boldIndex) => {
      if (boldPart.startsWith('**') && boldPart.endsWith('**')) {
        return (
          <strong key={`${index}-${boldIndex}`}>{boldPart.slice(2, -2)}</strong>
        );
      }
      // Handle line breaks
      return boldPart.split('\n').map((line, lineIndex, arr) => (
        <React.Fragment key={`${index}-${boldIndex}-${lineIndex}`}>
          {line}
          {lineIndex < arr.length - 1 && <br />}
        </React.Fragment>
      ));
    });
  });
};

// Feature Card Component - uses CSS variable for primary color
// Height determined by grid layout (all rows equal height)
const FeatureCard: React.FC<{ item: IntroFeatureItem }> = ({ item }) => {
  return (
    <div className="flex items-start gap-3 p-4 bg-[var(--color-fill-1)] rounded-lg border border-[var(--color-border-1)] h-full transition-all duration-200 hover:border-[var(--color-border-3)] hover:shadow-sm">
      <div className="w-9 h-9 rounded-lg flex items-center justify-center text-lg flex-shrink-0 bg-[var(--color-primary)]">
        {item.icon}
      </div>
      <div className="flex-1 overflow-hidden">
        <h4
          className="text-sm font-semibold text-[var(--color-text-1)] m-0 mb-1 truncate"
          title={item.title}
        >
          {item.title}
        </h4>
        <p
          className="text-[13px] text-[var(--color-text-3)] m-0 leading-relaxed line-clamp-3"
          title={item.description}
        >
          {item.description}
        </p>
      </div>
    </div>
  );
};

// Section Title Component - uses CSS variable for primary color
const SectionTitle: React.FC<{ title: string }> = ({ title }) => {
  return (
    <div className="flex items-center gap-2 mb-4">
      <span className="w-1 h-[18px] rounded-sm flex-shrink-0 bg-[var(--color-primary)]" />
      <Title
        level={4}
        className="!m-0 !text-base !font-semibold !text-[var(--color-text-1)]"
      >
        {title}
      </Title>
    </div>
  );
};

// Field Table Component - uses CSS variable for primary color
const FieldTableSection: React.FC<{ table: IntroFieldTable }> = ({ table }) => {
  const columns: ColumnsType<Record<string, string>> = table.columns.map(
    (col) => ({
      title: col.title,
      dataIndex: col.key,
      key: col.key,
      width: col.width,
      render: (text: string) => {
        // First column usually contains field names - style them specially
        if (col.key === table.columns[0]?.key) {
          return (
            <span className="font-mono text-xs text-[var(--color-primary)]">
              {text}
            </span>
          );
        }
        return text;
      }
    })
  );

  return (
    <div className="mb-6 last:mb-0">
      {table.title && <SectionTitle title={table.title} />}
      {table.description && (
        <Paragraph className="text-sm text-[var(--color-text-2)] mb-3">
          {table.description}
        </Paragraph>
      )}
      <Table
        columns={columns as ColumnsType<any>}
        dataSource={table.data.map((row, index) => ({ ...row, key: index }))}
        pagination={false}
        size="small"
      />
    </div>
  );
};

// Tip/Alert Component
const TipSection: React.FC<{ tip: IntroTip }> = ({ tip }) => {
  return (
    <Alert
      type={tip.type}
      showIcon
      message={tip.title}
      description={
        <div className="text-[13px] leading-relaxed">
          {parseSimpleMarkdown(tip.content)}
        </div>
      }
      className="mt-4 rounded-lg [&_.ant-alert-message]:font-semibold [&_.ant-alert-description]:mt-2"
    />
  );
};

// Code Block Component
const CodeBlockSection: React.FC<{ codeBlock: IntroCodeBlock }> = ({
  codeBlock
}) => {
  return (
    <div className="mt-4">
      {codeBlock.title && (
        <h4 className="text-sm font-semibold text-[var(--color-text-1)] m-0 mb-3">
          {codeBlock.title}
        </h4>
      )}
      <pre className="bg-[#1e1e1e] rounded-lg p-4 m-0 overflow-x-auto">
        <code className="text-[#d4d4d4] font-mono text-[13px] leading-relaxed whitespace-pre-wrap break-all">
          {codeBlock.code}
        </code>
      </pre>
    </div>
  );
};

// Best Practices Component
const BestPracticesSection: React.FC<{ title: string; items: string[] }> = ({
  title,
  items
}) => {
  return (
    <div>
      <SectionTitle title={title} />
      <ul className="pl-5 m-0">
        {items.map((item, index) => (
          <li
            key={index}
            className="text-sm text-[var(--color-text-2)] leading-8 [&_strong]:text-[var(--color-text-1)]"
          >
            {parseSimpleMarkdown(item)}
          </li>
        ))}
      </ul>
    </div>
  );
};

// Steps Component - uses CSS variable for primary color
const StepsSection: React.FC<{
  title: string;
  description?: string;
  items: { title: string; description: string; code?: string }[];
}> = ({ title, description, items }) => {
  return (
    <div>
      <SectionTitle title={title} />
      {description && (
        <Paragraph className="text-sm text-[var(--color-text-2)] mb-0">
          {description}
        </Paragraph>
      )}
      {items.length > 0 && (
        <div className="mt-4">
          {items.map((item, index) => (
            <div key={index} className="flex gap-4 mb-6 last:mb-0">
              <div className="w-7 h-7 rounded-full flex items-center justify-center text-white text-sm font-semibold flex-shrink-0 bg-[var(--color-primary)]">
                {index + 1}
              </div>
              <div className="flex-1">
                <h4 className="text-sm font-semibold text-[var(--color-text-1)] m-0 mb-2">
                  {item.title}
                </h4>
                <p className="text-[13px] text-[var(--color-text-2)] leading-relaxed m-0">
                  {parseSimpleMarkdown(item.description)}
                </p>
                {item.code && (
                  <pre className="bg-[var(--color-fill-2)] rounded p-3 mt-3 overflow-x-auto">
                    <code className="font-mono text-xs text-[var(--color-text-1)]">
                      {item.code}
                    </code>
                  </pre>
                )}
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
};

// Main IntroRenderer Component
const IntroRenderer: React.FC<IntroRendererProps> = ({
  filePath,
  fileName,
  config: externalConfig
}) => {
  const [loading, setLoading] = useState<boolean>(true);
  const [config, setConfig] = useState<IntroConfig | null>(null);
  const locale =
    typeof window !== 'undefined' ? localStorage.getItem('locale') : 'zh';

  const fetchConfig = async () => {
    if (!filePath || !fileName) return;

    try {
      setLoading(true);
      const requestUrl = `/api/json?filePath=${filePath}/${locale === 'en' ? 'en' : 'zh'}/${fileName}.json`;
      const response = await fetch(requestUrl);

      if (!response.ok) {
        throw new Error('Failed to fetch introduction config');
      }

      const data = await response.json();
      setConfig(data);
    } catch (error) {
      console.error('Failed to load introduction config:', error);
      message.error('Failed to load introduction content.');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    if (externalConfig) {
      setConfig(externalConfig);
      setLoading(false);
      return;
    }

    if (!filePath || !fileName) {
      setLoading(false);
      return;
    }

    fetchConfig();
  }, [filePath, fileName, externalConfig, locale]);

  if (loading) {
    return (
      <div className="flex justify-center items-center min-h-[200px]">
        <Spin size="large" />
      </div>
    );
  }

  if (!config) {
    return (
      <div className="flex justify-center items-center min-h-[200px] text-[var(--color-text-3)]">
        <Text type="secondary">No introduction content available.</Text>
      </div>
    );
  }

  return (
    <div className="p-0">
      {/* Overview Section */}
      {config.overview && (
        <section className="mb-8 last:mb-0">
          <SectionTitle title={config.overview.title} />
          {config.overview.paragraphs.map((paragraph, index) => (
            <Paragraph
              key={index}
              className="text-sm text-[var(--color-text-2)] leading-relaxed mb-3 last:mb-0"
            >
              {parseSimpleMarkdown(paragraph)}
            </Paragraph>
          ))}
        </section>
      )}

      {/* Features Section */}
      {config.features && (
        <section className="mb-8 last:mb-0">
          <SectionTitle title={config.features.title} />
          <div className="grid grid-cols-1 sm:grid-cols-2 xl:grid-cols-3 2xl:grid-cols-4 gap-4 mt-4 auto-rows-fr">
            {config.features.items.map((item, index) => (
              <FeatureCard key={index} item={item} />
            ))}
          </div>
        </section>
      )}

      {/* Field Tables Section */}
      {config.fieldTables && config.fieldTables.length > 0 && (
        <section className="mb-8 last:mb-0">
          {config.fieldTables.map((table, index) => (
            <FieldTableSection key={index} table={table} />
          ))}
        </section>
      )}

      {/* Steps Section */}
      {config.steps && (
        <section className="mb-8 last:mb-0">
          <StepsSection
            title={config.steps.title}
            description={config.steps.description}
            items={config.steps.items}
          />
        </section>
      )}

      {/* Tips Section */}
      {config.tips && config.tips.length > 0 && (
        <section className="mb-8 last:mb-0">
          {config.tips.map((tip, index) => (
            <TipSection key={index} tip={tip} />
          ))}
        </section>
      )}

      {/* Code Blocks Section */}
      {config.codeBlocks && config.codeBlocks.length > 0 && (
        <section className="mb-8 last:mb-0">
          {config.codeBlocks.map((codeBlock, index) => (
            <CodeBlockSection key={index} codeBlock={codeBlock} />
          ))}
        </section>
      )}

      {/* Best Practices Section */}
      {config.bestPractices && (
        <section className="mb-8 last:mb-0">
          <BestPracticesSection
            title={config.bestPractices.title}
            items={config.bestPractices.items}
          />
        </section>
      )}
    </div>
  );
};

export default IntroRenderer;
