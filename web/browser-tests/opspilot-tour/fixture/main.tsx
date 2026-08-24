import '@ant-design/v5-patch-for-react-19';
import { Tour } from 'antd';
import { useEffect, useRef, useState } from 'react';
import { createRoot } from 'react-dom/client';

const OpsPilotTourFixture = () => {
  const modelMenuRef = useRef<HTMLAnchorElement>(null);
  const [open, setOpen] = useState(false);

  useEffect(() => {
    setOpen(true);
  }, []);

  return (
    <div style={{ minWidth: 1280, minHeight: '100vh' }}>
      <header style={{ height: 56, position: 'sticky', top: 0, zIndex: 1000 }}>
        <nav
          aria-label="OpsPilot"
          style={{ display: 'flex', justifyContent: 'center', alignItems: 'center', height: '100%', gap: 32 }}
        >
          {['工作台', '智能体', '知识库', '工具', '记忆'].map((label) => (
            <a key={label}>{label}</a>
          ))}
          <a ref={modelMenuRef} id="provide_list" style={{ padding: '12px 20px' }}>
            模型
          </a>
        </nav>
      </header>
      <main style={{ height: 720, background: '#f4f6f9' }} />
      <Tour
        open={open}
        onClose={() => setOpen(false)}
        steps={[
          {
            title: '第一步: 接入LLM大模型',
            description: '使用内置的大模型，或者自行接入大模型，以便智能体使用。',
            target: () => modelMenuRef.current || document.body,
          },
        ]}
      />
    </div>
  );
};

const root = document.getElementById('root');

if (!root) {
  throw new Error('Missing fixture root');
}

createRoot(root).render(<OpsPilotTourFixture />);
