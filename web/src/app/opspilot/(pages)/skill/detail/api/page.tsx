import React from 'react';
import MarkdownRenderer from '@/components/markdown';

const SkillApiDocsPage: React.FC = () => {
  return (
    <div>
      <MarkdownRenderer filePath="module_api/" fileName="skill_api" />
    </div>
  );
};

export default SkillApiDocsPage;
