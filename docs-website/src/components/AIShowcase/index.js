import clsx from 'clsx';
import Heading from '@theme/Heading';
import styles from './styles.module.css';

const platformFeatures = [
  {
    icon: '🔒',
    title: '涉密环境支持',
    description: '端到端安全架构，满足等保三级要求，为关键系统提供可信运行环境',
    badge: '安全可信',
    color: 'purple',
    metric: '等保三级',
    highlights: ['国密算法', '数据隔离']
  },
  {
    icon: '⚡',
    title: '极致轻量',
    description: '优化架构设计与资源调度，在保障能力的同时显著降低系统能耗',
    badge: '高效节能',
    color: 'green',
    metric: '50%↓能耗',
    highlights: ['智能调度', '绿色运维']
  },
  {
    icon: '💰',
    title: '成本优化',
    description: '简化部署与运维流程，通过自动化大幅降低总体持有成本',
    badge: 'TCO优化',
    color: 'blue',
    metric: '60%↓成本',
    highlights: ['自动运维', '按需扩展']
  },
  {
    icon: '🚀',
    title: '边缘自治',
    description: '支持边缘环境独立运行，具备断网续航与故障自愈能力',
    badge: '边缘计算',
    color: 'orange',
    metric: '离线运行',
    highlights: ['自动修复', '智能决策']
  },
  {
    icon: '🤖',
    title: 'AI 原生',
    description: '深度集成大模型能力，提供智能诊断、决策辅助与自动修复',
    badge: 'AI驱动',
    color: 'indigo',
    metric: '智能预测',
    highlights: ['智能诊断', '自主修复']
  },
  {
    icon: '📈',
    title: '无感扩容',
    description: '一体机模式即插即用，新节点自动识别并纳管，平滑扩展集群',
    badge: '弹性伸缩',
    color: 'teal',
    metric: '即插即用',
    highlights: ['零配置', '平滑扩展']
  },
  {
    icon: '🌍',
    title: '国际化',
    description: '支持多语言界面与多地区合规适配，满足全球化部署需求',
    badge: '全球化',
    color: 'cyan',
    metric: '多语言',
    highlights: ['合规适配', '全球部署']
  },
  {
    icon: '🔗',
    title: '开放生态',
    description: '提供完善的插件体系与开放API，支持第三方系统深度集成',
    badge: '生态开放',
    color: 'pink',
    metric: '开放API',
    highlights: ['插件系统', '生态集成']
  }
];

function PlatformFeature({ icon, title, description, badge, color, metric, highlights }) {
  return (
    <div className={styles.platformFeatureItem}>
      <div className={clsx(styles.platformFeatureCard, styles[color])}>
        <div className={styles.cardHeader}>
          <div className={styles.platformFeatureIcon}>
            <span className={styles.iconEmoji}>{icon}</span>
          </div>
          <div className={styles.cardBadge}>{badge}</div>
        </div>

        <div className={styles.platformFeatureContent}>
          <Heading as="h3" className={styles.platformFeatureTitle}>
            {title}
          </Heading>
          <p className={styles.platformFeatureDescription}>
            {description}
          </p>

          <div className={styles.metricHighlight}>
            <span className={styles.metricValue}>{metric}</span>
            <div className={styles.highlightTags}>
              {highlights.map((highlight, idx) => (
                <span key={idx} className={styles.highlightTag}>
                  {highlight}
                </span>
              ))}
            </div>
          </div>
        </div>

        <div className={styles.cardGlow}></div>
      </div>
    </div>
  );
}

export default function PlatformShowcase() {
  return (
    <section className={styles.platformShowcase}>
      <div className={styles.container}>
        <div className={styles.sectionHeader}>
          <Heading as="h2" className={styles.sectionTitle}>
            关键特性
          </Heading>
        </div>

        <div className={styles.platformFeatureGrid}>
          {platformFeatures.map((feature, idx) => (
            <PlatformFeature key={idx} {...feature} />
          ))}
        </div>
      </div>
    </section>
  );
}