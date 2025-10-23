import React from 'react';

// AI 回复的富文本模板
export const mockAIResponses = {
  // 表格响应
  table: () => (
    <div>
      <p style={{ marginBottom: '8px' }}>这是一个服务器状态对比表格：</p>
      <table
        style={{
          width: '100%',
          borderCollapse: 'collapse',
          fontSize: '11px',
          backgroundColor: '#fff',
          borderRadius: '4px',
          overflow: 'hidden',
        }}
      >
        <thead>
          <tr style={{ backgroundColor: '#f5f5f5' }}>
            <th
              style={{
                padding: '6px 4px',
                border: '1px solid #e0e0e0',
                textAlign: 'left',
              }}
            >
              服务器
            </th>
            <th
              style={{
                padding: '6px 4px',
                border: '1px solid #e0e0e0',
                textAlign: 'center',
              }}
            >
              状态
            </th>
            <th
              style={{
                padding: '6px 4px',
                border: '1px solid #e0e0e0',
                textAlign: 'center',
              }}
            >
              CPU
            </th>
            <th
              style={{
                padding: '6px 4px',
                border: '1px solid #e0e0e0',
                textAlign: 'center',
              }}
            >
              内存
            </th>
          </tr>
        </thead>
        <tbody>
          <tr>
            <td style={{ padding: '6px 4px', border: '1px solid #e0e0e0' }}>
              Server-01
            </td>
            <td
              style={{
                padding: '6px 4px',
                border: '1px solid #e0e0e0',
                textAlign: 'center',
              }}
            >
              <span style={{ color: '#52c41a' }}>● 正常</span>
            </td>
            <td
              style={{
                padding: '6px 4px',
                border: '1px solid #e0e0e0',
                textAlign: 'center',
              }}
            >
              45%
            </td>
            <td
              style={{
                padding: '6px 4px',
                border: '1px solid #e0e0e0',
                textAlign: 'center',
              }}
            >
              62%
            </td>
          </tr>
          <tr>
            <td style={{ padding: '6px 4px', border: '1px solid #e0e0e0' }}>
              Server-02
            </td>
            <td
              style={{
                padding: '6px 4px',
                border: '1px solid #e0e0e0',
                textAlign: 'center',
              }}
            >
              <span style={{ color: '#ff4d4f' }}>● 异常</span>
            </td>
            <td
              style={{
                padding: '6px 4px',
                border: '1px solid #e0e0e0',
                textAlign: 'center',
              }}
            >
              89%
            </td>
            <td
              style={{
                padding: '6px 4px',
                border: '1px solid #e0e0e0',
                textAlign: 'center',
              }}
            >
              95%
            </td>
          </tr>
          <tr>
            <td style={{ padding: '6px 4px', border: '1px solid #e0e0e0' }}>
              Server-03
            </td>
            <td
              style={{
                padding: '6px 4px',
                border: '1px solid #e0e0e0',
                textAlign: 'center',
              }}
            >
              <span style={{ color: '#52c41a' }}>● 正常</span>
            </td>
            <td
              style={{
                padding: '6px 4px',
                border: '1px solid #e0e0e0',
                textAlign: 'center',
              }}
            >
              32%
            </td>
            <td
              style={{
                padding: '6px 4px',
                border: '1px solid #e0e0e0',
                textAlign: 'center',
              }}
            >
              58%
            </td>
          </tr>
        </tbody>
      </table>
    </div>
  ),

  // 代码响应
  code: () => (
    <div>
      <p style={{ marginBottom: '8px' }}>这是一个 Python 示例代码：</p>
      <pre
        style={{
          backgroundColor: '#1e1e1e',
          color: '#d4d4d4',
          padding: '12px',
          borderRadius: '6px',
          overflow: 'auto',
          fontSize: '12px',
          fontFamily: 'Monaco, Consolas, monospace',
        }}
      >
        {`def hello_world():
    """打印 Hello World"""
    print("Hello, World!")
    return True

# 调用函数
if __name__ == "__main__":
    hello_world()`}
      </pre>
    </div>
  ),

  // 卡片响应
  card: () => (
    <div>
      <div
        style={{
          backgroundColor: '#fff',
          border: '1px solid #e0e0e0',
          borderRadius: '8px',
          padding: '12px',
          marginBottom: '8px',
        }}
      >
        <div
          style={{
            display: 'flex',
            alignItems: 'center',
            marginBottom: '8px',
          }}
        >
          <div
            style={{
              width: '40px',
              height: '40px',
              borderRadius: '50%',
              backgroundColor: '#1677ff',
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
              color: '#fff',
              fontSize: '20px',
              marginRight: '10px',
            }}
          >
            📊
          </div>
          <div>
            <div style={{ fontWeight: 'bold', fontSize: '14px' }}>
              系统监控报告
            </div>
            <div style={{ fontSize: '12px', color: '#999' }}>
              2025-01-16 10:30
            </div>
          </div>
        </div>
        <div style={{ fontSize: '13px', color: '#666', lineHeight: '1.6' }}>
          系统运行正常，CPU 使用率 45%，内存使用率 62%。
        </div>
        <div
          style={{
            marginTop: '10px',
            paddingTop: '10px',
            borderTop: '1px solid #f0f0f0',
            display: 'flex',
            justifyContent: 'space-between',
            fontSize: '12px',
          }}
        >
          <span style={{ color: '#52c41a' }}>✓ 所有服务正常</span>
          <span style={{ color: '#1677ff' }}>查看详情 →</span>
        </div>
      </div>
    </div>
  ),

  // 列表响应
  list: () => (
    <div>
      <p style={{ marginBottom: '8px', fontWeight: 'bold' }}>📋 任务清单</p>
      <div
        style={{
          backgroundColor: '#fff',
          border: '1px solid #e0e0e0',
          borderRadius: '6px',
          overflow: 'hidden',
        }}
      >
        {[
          { text: '完成系统部署', status: 'done' },
          { text: '配置监控告警', status: 'done' },
          { text: '性能优化测试', status: 'progress' },
          { text: '编写技术文档', status: 'pending' },
        ].map((item, index) => (
          <div
            key={index}
            style={{
              padding: '10px 12px',
              borderBottom: index < 3 ? '1px solid #f0f0f0' : 'none',
              display: 'flex',
              alignItems: 'center',
              gap: '8px',
            }}
          >
            <span style={{ fontSize: '16px' }}>
              {item.status === 'done'
                ? '✅'
                : item.status === 'progress'
                ? '🔄'
                : '⭕'}
            </span>
            <span
              style={{
                fontSize: '13px',
                color: item.status === 'done' ? '#999' : '#333',
                textDecoration:
                  item.status === 'done' ? 'line-through' : 'none',
              }}
            >
              {item.text}
            </span>
          </div>
        ))}
      </div>
    </div>
  ),
};

// 文本响应模板
export const mockTextResponses = {
  product:
    '我们的产品具有以下核心功能：\n\n• 🚀 智能运维自动化\n• 📊 实时监控告警\n• 🔧 故障快速定位\n• 💡 AI 智能分析\n\n您想了解哪个功能的详细信息？试试发送"表格"、"代码"、"卡片"或"列表"查看更多展示效果！',

  support:
    '我很乐意为您提供技术支持！请告诉我您遇到的具体问题：\n\n• 🔍 系统配置问题\n• 🐛 故障排查\n• 📋 使用指南\n• 🔗 集成对接\n\n我会尽快为您解答。',

  thanks: '不客气！😊 很高兴能帮助到您。如果还有其他问题,随时可以问我！',

  help: '我是您的AI助手，可以帮您：\n\n🔹 产品功能咨询\n🔹 技术问题解答\n🔹 使用指导\n🔹 故障排查\n\n💡 试试这些命令：\n• 发送"表格" - 查看表格展示\n• 发送"代码" - 查看代码高亮\n• 发送"卡片" - 查看卡片样式\n• 发送"列表" - 查看任务列表',

  default: [
    '我理解您的问题，让我为您详细解答...',
    '这是一个很好的问题！根据我的了解...',
    '关于这个问题，我建议您...',
    '我来帮您分析一下这个情况...',
  ],
};
