import clsx from 'clsx';
import Heading from '@theme/Heading';
import styles from './styles.module.css';

const platformFeatures = [
  {
    icon: '🔒',
    title: '涉密环境支持',
    description: '端到端安全保障，确保敏感数据和关键系统安全运行',
    badge: '安全可信',
    color: 'purple',
    metric: '等保三级',
    highlights: ['国密算法', '数据隔离']
  },
  {
    icon: '⚡',
    title: '能耗比高',
    description: '轻量化架构设计，优化资源调度大幅降低系统能耗',
    badge: '绿色节能', 
    color: 'green',
    metric: '50%↓能耗',
    highlights: ['智能调度', '绿色运维']
  },
  {
    icon: '💰',
    title: '持有成本低',
    description: '简化部署流程，通过自动化显著减少总体持有成本',
    badge: '成本优化',
    color: 'blue',
    metric: '60%↓成本',
    highlights: ['免运维', '按需付费']
  },
  {
    icon: '🚀',
    title: '边缘自治',
    description: '支持边缘环境自主运行，具备断网续航和故障自愈能力',
    badge: '边缘计算',
    color: 'orange',
    metric: '边缘运行',
    highlights: ['自动修复', '智能决策']
  },
  {
    icon: '🤖',
    title: 'AI原生',
    description: '底层架构融入AI能力，提供智能运维和自主修复能力',
    badge: 'AI驱动',
    color: 'indigo',
    metric: '智能预测',
    highlights: ['自动化', 'ML集成']
  },
  {
    icon: '📈',
    title: '无感扩容',
    description: '一体机模式下即插即用，插上网线就能自动识别并扩容节点',
    badge: '弹性伸缩',
    color: 'teal',
    metric: '自动扩容',
    highlights: ['即插即用', '平滑扩展']
  },
  {
    icon: '🌍',
    title: '国际化',
    description: '支持多语言界面，适配不同地区使用需求',
    badge: '全球化',
    color: 'cyan',
    metric: '多语言',
    highlights: ['合规适配', '全球部署']
  },
  {
    icon: '🔗',
    title: '生态化',
    description: '开放插件体系和API，支持第三方系统集成',
    badge: '开放生态',
    color: 'pink',
    metric: '开放API',
    highlights: ['插件系统', '生态集成']
  }
];

function PlatformFeature({icon, title, description, badge, color, metric, highlights}) {
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
          <p className={styles.sectionSubtitle}>
            轻量化架构下的核心能力，满足智能运维全场景需求
          </p>
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