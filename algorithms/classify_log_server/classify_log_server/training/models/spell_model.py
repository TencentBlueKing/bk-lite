"""用于日志聚类的 Spell 模型实现。"""

from typing import Any, Dict, List, Optional, Tuple, Set
from collections import Counter, defaultdict
from datetime import datetime
import time

import mlflow
from loguru import logger

from .base import BaseLogClusterModel, ModelRegistry


@ModelRegistry.register("Spell")
class SpellModel(BaseLogClusterModel):
    """
    用于日志聚类的 Spell 模型。
    
    Spell (Streaming Parser for Event Logs using LCS) 是一个在线日志解析器，
    使用最长公共子序列 (LCS) 来识别日志模板。
    
    论文："Spell: Online Streaming Parsing of Large Unstructured System Logs"
    """

    def __init__(self, **kwargs):
        """
        初始化 Spell 模型。

        Args:
            **kwargs: 模型配置参数
                - tau: LCS 相似度阈值 (默认 0.5)
                - use_position_weight: 是否启用位置权重 (默认 True)
                - position_weight_config: 位置权重配置 (可选)
                - use_cache: 是否启用 LCS 缓存 (默认 True)
                - merge_threshold: 聚类合并阈值 (默认 0.85)
                - diversity_threshold: Token 多样性阈值 (默认 3)
                - min_cluster_size: 最小聚类大小 (默认 5)
                - enable_explain: 是否启用可解释性 (默认 True)
        """
        # 核心参数
        self.tau = kwargs.get("tau", 0.5)
        
        # 位置权重配置
        self.use_position_weight = kwargs.get("use_position_weight", True)
        self.position_weight_config = kwargs.get("position_weight_config") or {
            'head_count': 3,
            'head_weight': 2.0,
            'tail_count': 2,
            'tail_weight': 1.5,
            'middle_weight': 1.0,
        }
        
        # 优化参数
        self.use_cache = kwargs.get("use_cache", True)
        self.merge_threshold = kwargs.get("merge_threshold", 0.85)
        self.diversity_threshold = kwargs.get("diversity_threshold", 3)
        self.min_cluster_size = kwargs.get("min_cluster_size", 5)
        
        # 可解释性
        self.enable_explain = kwargs.get("enable_explain", True)
        
        # 初始化内部状态
        self.clusters = []  # 聚类列表
        self.token_index = defaultdict(set)  # 倒排索引
        self.lcs_cache = {} if self.use_cache else None
        self.raw_logs = []  # 存储原始日志（用于可解释性）
        
        super().__init__(config=kwargs)
        logger.info(f"SpellModel initialized with tau={self.tau}, use_position_weight={self.use_position_weight}")

    def fit(
        self, 
        data: List[str], 
        val_data: Optional[List[str]] = None,
        verbose: bool = True,
        log_to_mlflow: bool = True
    ) -> "SpellModel":
        """
        在日志上训练 Spell 模型。

        Args:
            data: 预处理后的日志消息列表（训练数据）
            val_data: 验证数据（可选，未使用）
            verbose: 是否输出详细日志
            log_to_mlflow: 是否记录到 MLflow
            
        Returns:
            self (支持链式调用)
        """
        if verbose:
            logger.info(f"训练 Spell 模型，数据量: {len(data)} 条日志")
            logger.info(f"参数: tau={self.tau}, use_position_weight={self.use_position_weight}, merge_threshold={self.merge_threshold}")
        
        start_time = time.time()
        
        # 1. 初始化状态
        self.clusters = []
        self.token_index = defaultdict(set)
        if self.lcs_cache is not None:
            self.lcs_cache.clear()
        self.raw_logs = []
        
        # 统计信息
        stats = {
            'matched': 0,
            'new_cluster': 0,
            'total_candidates': 0,
            'quick_filtered': 0,
        }
        
        # 2. 逐条处理日志
        for log_idx, log in enumerate(data):
            tokens = self._tokenize(log)
            
            if not tokens:
                continue
            
            # 存储原始日志（用于可解释性）
            if self.enable_explain:
                self.raw_logs.append(log)
            
            # 3. 查找匹配的聚类
            best_cluster_id = -1
            best_similarity = 0.0
            
            # 使用倒排索引快速获取候选聚类
            candidate_clusters = set()
            for token in tokens:
                if token in self.token_index:
                    candidate_clusters.update(self.token_index[token])
            
            stats['total_candidates'] += len(candidate_clusters)
            
            # 快速过滤 + LCS 匹配
            for cluster_id in candidate_clusters:
                cluster = self.clusters[cluster_id]
                template = cluster['template']
                
                # 快速过滤
                if not self._quick_filter(tokens, template):
                    stats['quick_filtered'] += 1
                    continue
                
                # 计算 LCS 相似度
                similarity = self._lcs_similarity(tokens, template)
                
                if similarity > best_similarity:
                    best_similarity = similarity
                    best_cluster_id = cluster_id
            
            # 4. 更新或创建聚类
            if best_similarity >= self.tau:
                # 匹配现有聚类
                stats['matched'] += 1
                cluster = self.clusters[best_cluster_id]
                cluster['log_ids'].append(log_idx)
                
                # 更新模板（多数投票）
                cluster['logs'].append(tokens)
                cluster['template'] = self._update_template(cluster['logs'])
                
            else:
                # 创建新聚类
                stats['new_cluster'] += 1
                cluster_id = len(self.clusters)
                
                new_cluster = {
                    'id': cluster_id,
                    'template': tokens[:],  # 初始模板就是当前日志
                    'logs': [tokens],
                    'log_ids': [log_idx],
                }
                
                self.clusters.append(new_cluster)
                
                # 更新倒排索引
                for token in tokens:
                    self.token_index[token].add(cluster_id)
            
            # 进度输出
            if verbose and (log_idx + 1) % 10000 == 0:
                elapsed = time.time() - start_time
                logger.info(f"  处理进度: {log_idx + 1}/{len(data)} ({(log_idx+1)/len(data)*100:.1f}%), "
                           f"聚类数: {len(self.clusters)}, 用时: {elapsed:.1f}s")
        
        # 5. 聚类合并
        if self.merge_threshold > 0 and len(self.clusters) > 1:
            if verbose:
                logger.info(f"开始聚类合并，阈值: {self.merge_threshold}")
            original_count = len(self.clusters)
            self._merge_clusters()
            if verbose:
                logger.info(f"聚类合并完成: {original_count} -> {len(self.clusters)}")
        
        # 6. 提取模板
        self.templates = []
        for cluster in self.clusters:
            template_str = ' '.join(cluster['template'])
            self.templates.append(template_str)
        
        # 7. 保存训练数据的聚类分配（用于生成可视化）
        self._last_predictions = []
        for cluster in self.clusters:
            cluster_id = cluster['id']
            log_count = len(cluster['log_ids'])
            self._last_predictions.extend([cluster_id] * log_count)
        
        self.is_trained = True
        
        elapsed_time = time.time() - start_time
        
        if verbose:
            logger.info(f"训练完成，发现 {len(self.templates)} 个模板")
            logger.info(f"训练统计: 匹配={stats['matched']}, 新建={stats['new_cluster']}")
            logger.info(f"候选过滤: 总候选={stats['total_candidates']}, 快速过滤={stats['quick_filtered']}")
            logger.info(f"训练耗时: {elapsed_time:.2f}s")
        
        # 记录到 MLflow
        if log_to_mlflow and mlflow.active_run():
            try:
                mlflow.log_param("tau", self.tau)
                mlflow.log_param("use_position_weight", self.use_position_weight)
                mlflow.log_param("merge_threshold", self.merge_threshold)
                mlflow.log_metric("num_templates", len(self.templates))
                mlflow.log_metric("training_time", elapsed_time)
                mlflow.log_metric("matched_logs", stats['matched'])
                mlflow.log_metric("new_clusters", stats['new_cluster'])
            except Exception as e:
                logger.warning(f"MLflow 记录失败: {e}")
        
        return self

    def _check_fitted(self):
        """检查模型是否已训练
        
        Raises:
            RuntimeError: 模型未训练
        """
        if not self.is_trained:
            raise RuntimeError(
                "模型未训练，请先调用 fit() 方法"
            )

    def predict(self, logs: List[str]) -> List[int]:
        """
        预测日志的聚类 ID。

        Args:
            logs: 预处理后的日志消息列表

        Returns:
            聚类 ID 列表（模板 ID）
        """
        self._check_fitted()

        cluster_ids = []

        for log in logs:
            tokens = self._tokenize(log)
            
            if not tokens:
                cluster_ids.append(-1)
                continue
            
            # 查找最佳匹配聚类
            best_cluster_id = -1
            best_similarity = 0.0
            
            # 使用倒排索引快速获取候选聚类
            candidate_clusters = set()
            for token in tokens:
                if token in self.token_index:
                    candidate_clusters.update(self.token_index[token])
            
            # 如果没有候选，尝试所有聚类（fallback）
            if not candidate_clusters:
                candidate_clusters = set(range(len(self.clusters)))
            
            # 快速过滤 + LCS 匹配
            for cluster_id in candidate_clusters:
                cluster = self.clusters[cluster_id]
                template = cluster['template']
                
                # 快速过滤
                if not self._quick_filter(tokens, template):
                    continue
                
                # 计算 LCS 相似度
                similarity = self._lcs_similarity(tokens, template)
                
                if similarity > best_similarity:
                    best_similarity = similarity
                    best_cluster_id = cluster_id
            
            # 如果相似度达到阈值，返回聚类 ID，否则返回 -1
            if best_similarity >= self.tau:
                cluster_ids.append(best_cluster_id)
            else:
                cluster_ids.append(-1)

        logger.info(f"Predicted cluster IDs for {len(logs)} logs")
        return cluster_ids

    def evaluate(
        self,
        logs: List[str],
        ground_truth: Optional[List[int]] = None,
        prefix: str = "",
        verbose: bool = True,
    ) -> Dict[str, float]:
        """评估 Spell 模型性能
        
        Args:
            logs: 日志消息列表
            ground_truth: 真实聚类标签（可选，用于监督评估）
            prefix: 指标名称前缀（如 "train", "test", "val"）
            verbose: 是否输出详细日志
        
        Returns:
            评估指标字典，包含：
            - num_templates: 模板数量
            - coverage_rate: 覆盖率（解析成功率）
            - template_diversity: 模板多样性（归一化熵）
            - template_quality_score: 模板质量得分（如果有模板）
            - grouping_accuracy: 分组准确率（如果有 ground_truth）
            - precision: 精确率（如果有 ground_truth）
            - recall: 召回率（如果有 ground_truth）
            - f1_score: F1分数（如果有 ground_truth）
        
        Raises:
            RuntimeError: 模型未训练
        """
        self._check_fitted()

        if verbose:
            eval_mode = prefix if prefix else "default"
            logger.info(f"评估模式: {eval_mode}")
            logger.info(f"日志数量: {len(logs)}")

        metrics = {}

        # 获取预测结果
        predictions = self.predict(logs)

        # 1. 计算无监督指标
        # 模板数量
        unique_templates = set(predictions)
        metrics["num_templates"] = len(unique_templates)

        # 覆盖率（成功解析的日志百分比）
        # 通常，未解析的日志聚类 ID = -1
        parsed_logs = sum(1 for p in predictions if p != -1)
        metrics["coverage_rate"] = parsed_logs / len(logs) if logs else 0.0

        # 模板多样性（归一化熵）
        if unique_templates:
            from collections import Counter
            import math

            cluster_counts = Counter(predictions)
            total = len(predictions)
            entropy = -sum(
                (count / total) * math.log2(count / total)
                for count in cluster_counts.values()
                if count > 0
            )
            max_entropy = math.log2(len(unique_templates))
            metrics["template_diversity"] = entropy / max_entropy if max_entropy > 0 else 0.0
        else:
            metrics["template_diversity"] = 0.0

        # 平均模板质量得分（如果模板可用）
        if self.templates:
            metrics["template_quality_score"] = self._compute_template_quality()

        # 2. 计算监督指标（如果提供真实标签）
        if ground_truth is not None:
            # 分组准确率（GA）
            if len(predictions) != len(ground_truth):
                raise ValueError("预测结果和真实标签长度必须相同")
            
            correct = sum(1 for p, g in zip(predictions, ground_truth) if p == g)
            metrics["grouping_accuracy"] = correct / len(predictions) if predictions else 0.0

            # 解析准确率（PA）
            # PA 通常通过比较预测模板和真实模板来计算
            # 这里为简化，使用与 GA 相同的值（可进一步优化）
            metrics["parsing_accuracy"] = metrics["grouping_accuracy"]

            # 精确率和召回率
            precision, recall = self._compute_precision_recall(predictions, ground_truth)
            metrics["precision"] = precision
            metrics["recall"] = recall
            
            # F1 分数
            if precision + recall > 0:
                metrics["f1_score"] = 2 * (precision * recall) / (precision + recall)
            else:
                metrics["f1_score"] = 0.0

        # 3. 存储内部数据（用于后续分析）
        metrics['_predictions'] = predictions
        if ground_truth is not None:
            metrics['_ground_truth'] = ground_truth

        # 4. 应用前缀（如果提供）
        if prefix:
            metrics = {f"{prefix}_{k}" if not k.startswith('_') else k: v 
                       for k, v in metrics.items()}

        if verbose:
            # 输出关键指标（排除内部数据）
            key_metrics = {k: v for k, v in metrics.items() if not k.startswith('_')}
            logger.info(f"评估结果: {key_metrics}")

        return metrics

    def _compute_precision_recall(
        self, predictions: List[int], ground_truth: List[int]
    ) -> tuple[float, float]:
        """计算聚类的精确率和召回率
        
        Args:
            predictions: 预测的聚类 ID
            ground_truth: 真实聚类 ID
        
        Returns:
            (精确率, 召回率) 元组
        """
        from collections import defaultdict

        # 构建聚类映射
        pred_clusters = defaultdict(set)
        true_clusters = defaultdict(set)

        for i, (p, g) in enumerate(zip(predictions, ground_truth)):
            pred_clusters[p].add(i)
            true_clusters[g].add(i)

        # 计算真正例（TP）
        tp = 0
        for cluster in pred_clusters.values():
            # 计算同一预测聚类中的配对数
            for i in cluster:
                for j in cluster:
                    if i < j and ground_truth[i] == ground_truth[j]:
                        tp += 1

        # 预测聚类中的总配对数
        pred_pairs = sum(
            len(cluster) * (len(cluster) - 1) // 2 for cluster in pred_clusters.values()
        )

        # 真实聚类中的总配对数
        true_pairs = sum(
            len(cluster) * (len(cluster) - 1) // 2 for cluster in true_clusters.values()
        )

        precision = tp / pred_pairs if pred_pairs > 0 else 0.0
        recall = tp / true_pairs if true_pairs > 0 else 0.0

        return precision, recall

    def _compute_template_quality(self) -> float:
        """计算平均模板质量得分
        
        模板质量通过以下方式衡量：
        - 长度得分（偏好较短的模板）
        - 多样性得分（唯一词元 / 总词元）
        
        Returns:
            平均模板质量得分（0-1）
        """
        if not self.templates:
            return 0.0

        quality_scores = []

        for template in self.templates:
            # 长度得分（偏好较短的模板）
            tokens = template.split()
            length_score = 1.0 / (1.0 + len(tokens) / 10)  # 按 10 个词元归一化

            # 多样性得分（唯一词元 / 总词元）
            diversity_score = len(set(tokens)) / len(tokens) if tokens else 0.0

            # 综合得分
            quality = (length_score + diversity_score) / 2
            quality_scores.append(quality)

        return sum(quality_scores) / len(quality_scores) if quality_scores else 0.0

    def _extract_templates(self) -> List[str]:
        """
        从训练好的 Spell 模型中提取日志模板。
        
        注：此方法仅用于兼容性，实际上 fit() 中已直接提取模板。

        Returns:
            日志模板列表
        """
        templates = []
        
        for cluster in self.clusters:
            template_str = ' '.join(cluster['template'])
            templates.append(template_str)
        
        logger.info(f"Extracted {len(templates)} templates from Spell model")
        return templates

    def get_log_groups(self) -> Dict[int, List[int]]:
        """
        获取日志组（聚类分配）。

        Returns:
            将聚类 ID 映射到日志索引列表的字典
        """
        self._check_fitted()

        log_groups = {}
        
        for cluster in self.clusters:
            cluster_id = cluster['id']
            log_ids = cluster['log_ids']
            log_groups[cluster_id] = log_ids

        return log_groups

    def get_template_by_id(self, cluster_id: int) -> Optional[str]:
        """
        通过聚类 ID 获取模板。

        Args:
            cluster_id: 聚类 ID

        Returns:
            模板字符串，如果未找到则返回 None
        """
        if cluster_id < 0 or cluster_id >= len(self.templates):
            return None

        return self.templates[cluster_id]

    def save(self, output_path: str) -> None:
        """
        将 Spell 模型保存到文件。

        Args:
            output_path: 输出文件路径
        """
        self._check_fitted()

        from pathlib import Path
        import joblib

        output_path = Path(output_path)
        output_path.parent.mkdir(parents=True, exist_ok=True)

        model_data = {
            "config": self.config,
            "templates": self.templates,
            "clusters": self.clusters,
            "tau": self.tau,
            "use_position_weight": self.use_position_weight,
            "position_weight_config": self.position_weight_config,
            "merge_threshold": self.merge_threshold,
            "diversity_threshold": self.diversity_threshold,
            "min_cluster_size": self.min_cluster_size,
            "is_trained": self.is_trained,
        }

        joblib.dump(model_data, output_path)
        logger.info(f"Spell model saved to {output_path}")

    def save_mlflow(self, artifact_path: str = "model") -> None:
        """将模型保存到 MLflow
        
        保存 Spell 模型、模板和配置，使其可用于推理服务。
        
        Args:
            artifact_path: MLflow artifact 路径
            
        Raises:
            RuntimeError: 模型未训练或序列化失败
        """
        self._check_fitted()
        
        logger.info("开始保存 Spell 模型到 MLflow")
        logger.info(f"artifact_path: {artifact_path}")
        logger.info(f"模板数量: {len(self.templates)}")
        logger.info(f"tau 参数: {self.tau}")
        
        # 1. 记录模型元数据
        if mlflow.active_run():
            metadata = {
                'model_type': 'Spell',
                'tau': self.tau,
                'num_templates': len(self.templates) if self.templates else 0,
                'is_trained': self.is_trained,
                'config': self.config,
            }
            
            try:
                mlflow.log_dict(metadata, "model_metadata.json")
                logger.info("✓ 元数据已记录")
            except Exception as e:
                logger.warning(f"元数据记录失败: {e}")
        
        # 2. 获取预处理器（如果有）
        preprocessor = getattr(self, 'preprocessor', None)
        if preprocessor:
            logger.info(f"✓ 发现预处理器: {type(preprocessor).__name__}")
        else:
            logger.warning("⚠ 未发现预处理器，推理时可能需要手动预处理")
        
        # 3. 创建 MLflow pyfunc Wrapper
        logger.info("创建 SpellWrapper...")
        from .spell_wrapper import SpellWrapper
        
        try:
            wrapped_model = SpellWrapper(model=self, preprocessor=preprocessor)
            logger.info("✓ Wrapper 创建成功")
        except Exception as e:
            logger.error(f"✗ Wrapper 创建失败: {type(e).__name__}: {e}")
            import traceback
            logger.error(f"详细错误:\n{traceback.format_exc()}")
            raise RuntimeError(f"SpellWrapper 创建失败: {e}")
        
        # 4. 测试 Wrapper 序列化
        logger.info("测试 Wrapper 序列化...")
        try:
            import cloudpickle
            serialized = cloudpickle.dumps(wrapped_model)
            logger.info(f"✓ Wrapper 序列化成功，大小: {len(serialized)} bytes")
            
            # 测试反序列化
            deserialized = cloudpickle.loads(serialized)
            logger.info(f"✓ Wrapper 反序列化成功: {type(deserialized)}")
        except Exception as e:
            logger.error(f"✗ Wrapper 序列化测试失败: {type(e).__name__}: {e}")
            import traceback
            logger.error(f"详细错误:\n{traceback.format_exc()}")
            raise RuntimeError(f"Wrapper 不可序列化: {e}")
        
        # 5. 保存模型到 MLflow
        logger.info("调用 mlflow.pyfunc.log_model()...")
        try:
            mlflow.pyfunc.log_model(
                artifact_path=artifact_path,
                python_model=wrapped_model,
                signature=None  # 设置为 None，支持灵活的输入格式
            )
            logger.info(f"✓ mlflow.pyfunc.log_model() 调用完成")
        except Exception as e:
            logger.error(f"✗ 模型保存失败: {type(e).__name__}: {e}")
            logger.error("可能原因:")
            logger.error("  1. Spell 模型包含不可序列化的对象（如 defaultdict、缓存等）")
            logger.error("  2. SpellWrapper 或预处理器序列化失败")
            logger.error("  3. 内存不足或磁盘空间不足")
            logger.error("  4. MLflow 服务连接问题")
            logger.error(f"调试信息: tau={self.tau}, templates={len(self.templates)}, preprocessor={getattr(self, 'preprocessor', None) is not None}")
            import traceback
            logger.error(f"详细错误:\n{traceback.format_exc()}")
            raise
        
        # 6. 验证模型是否真的保存了
        if mlflow.active_run():
            run_id = mlflow.active_run().info.run_id
            logger.info(f"验证模型文件是否存在 (Run ID: {run_id})...")
            try:
                client = mlflow.tracking.MlflowClient()
                artifacts = client.list_artifacts(run_id, artifact_path)
                if artifacts:
                    logger.info(f"✓ 发现 {len(artifacts)} 个 artifact 文件:")
                    for art in artifacts[:5]:  # 只显示前5个
                        logger.info(f"  - {art.path}")
                else:
                    logger.error(f"✗ artifact path '{artifact_path}' 下没有文件！")
                    raise RuntimeError(f"模型保存失败：artifact path '{artifact_path}' 为空")
            except Exception as e:
                logger.warning(f"无法验证 artifacts: {e}")
        
        # 7. 保存和记录模板（额外的 artifacts）
        templates = self.get_templates()
        if templates:
            try:
                from collections import Counter
                from ..mlflow_utils import MLFlowUtils
                
                # 尝试获取训练数据的聚类统计
                cluster_counts = None
                try:
                    if hasattr(self, '_last_predictions'):
                        cluster_counts = Counter(self._last_predictions)
                except:
                    pass
                
                # 保存模板
                MLFlowUtils.save_templates_artifact(
                    templates=templates,
                    cluster_counts=cluster_counts,
                    artifact_name="templates.txt"
                )
                logger.info(f"✓ 已记录 {len(templates)} 个模板到 templates.txt")
                
                # 生成模板分布可视化
                if cluster_counts:
                    try:
                        cluster_ids = list(cluster_counts.elements())
                        MLFlowUtils.plot_template_distribution(
                            cluster_ids=cluster_ids,
                            templates=templates,
                            top_n=20
                        )
                        MLFlowUtils.plot_cluster_size_distribution(
                            cluster_ids=cluster_ids
                        )
                        logger.info("✓ 模板分布可视化已生成")
                    except Exception as e:
                        logger.warning(f"生成模板可视化失败: {e}")
            except Exception as e:
                logger.warning(f"模板 artifact 记录失败（不影响模型保存）: {e}")
        
        logger.info(f"✓ 模型已成功保存到 MLflow: {artifact_path}")


    @classmethod
    def load(cls, model_path: str) -> "SpellModel":
        """
        从文件加载 Spell 模型。

        Args:
            model_path: 模型文件路径

        Returns:
            加载的 SpellModel 实例
        """
        from pathlib import Path
        import joblib

        model_path = Path(model_path)
        if not model_path.exists():
            raise FileNotFoundError(f"Model file not found: {model_path}")

        model_data = joblib.load(model_path)

        # 创建实例
        instance = cls(**model_data.get("config", {}))
        instance.templates = model_data["templates"]
        instance.clusters = model_data.get("clusters", [])
        instance.tau = model_data["tau"]
        instance.use_position_weight = model_data.get("use_position_weight", True)
        instance.position_weight_config = model_data.get("position_weight_config", instance.position_weight_config)
        instance.merge_threshold = model_data.get("merge_threshold", 0.85)
        instance.diversity_threshold = model_data.get("diversity_threshold", 3)
        instance.min_cluster_size = model_data.get("min_cluster_size", 5)
        instance.is_trained = model_data["is_trained"]
        
        # 重建倒排索引
        instance.token_index = defaultdict(set)
        for cluster in instance.clusters:
            cluster_id = cluster['id']
            for token in cluster['template']:
                if token != '<*>':
                    instance.token_index[token].add(cluster_id)

        logger.info(f"Spell model loaded from {model_path}")
        return instance

    def get_model_info(self) -> Dict[str, Any]:
        """
        获取模型信息。

        Returns:
            包含模型信息的字典
        """
        info = {
            "model_type": "Spell",
            "tau": self.tau,
            "num_templates": len(self.templates) if self.templates else 0,
            "is_trained": self.is_trained,
        }

        return info
    
    def optimize_hyperparams(
        self,
        train_data: List[str],
        val_data: List[str],
        config: Any
    ) -> Dict[str, Any]:
        """优化 Spell 超参数
        
        使用 Hyperopt 进行贝叶斯优化，主要优化 tau（LCS 相似度阈值）参数。
        
        Args:
            train_data: 训练日志列表
            val_data: 验证日志列表（用于评估不同超参数）
            config: 训练配置对象（包含搜索空间和优化设置）
            
        Returns:
            最优超参数字典
        """
        from hyperopt import fmin, tpe, hp, Trials, STATUS_OK, space_eval
        import numpy as np
        
        # 获取超参数优化配置
        hyperopt_config = config.get_hyperopt_config()
        max_evals = hyperopt_config["max_evals"]
        metric = hyperopt_config["metric"]
        search_space_config = hyperopt_config["search_space"]
        
        # 获取早停配置
        early_stop_config = hyperopt_config["early_stopping"]
        early_stop_enabled = early_stop_config.get("enabled", True)
        patience = early_stop_config.get("patience", 10)
        
        logger.info(
            f"开始超参数优化: max_evals={max_evals}, metric={metric}"
        )
        if early_stop_enabled:
            logger.info(f"早停机制: 启用 (patience={patience})")
        
        # 定义搜索空间
        space = self._build_search_space(search_space_config)
        
        # 优化状态跟踪
        trials = Trials()
        best_score = [0.0]  # 聚类质量指标越大越好
        eval_count = [0]
        failed_count = [0]
        
        def objective(params):
            eval_count[0] += 1
            current_eval = eval_count[0]
            
            try:
                # 准备参数
                decoded_params = self._decode_params(params, search_space_config)
                tau = decoded_params.get('tau', 0.5)
                merge_threshold = decoded_params.get('merge_threshold', 0.85)
                diversity_threshold = decoded_params.get('diversity_threshold', 3)
                
                param_str = f"tau={tau:.4f}"
                if 'merge_threshold' in decoded_params:
                    param_str += f", merge={merge_threshold:.4f}"
                if 'diversity_threshold' in decoded_params:
                    param_str += f", diversity={diversity_threshold}"
                
                logger.info(f"[{current_eval}/{max_evals}] 尝试参数: {param_str}")
                
                # 创建临时模型并训练
                temp_model = SpellModel(
                    tau=tau,
                    merge_threshold=merge_threshold,
                    diversity_threshold=diversity_threshold
                )
                temp_model.fit(train_data, verbose=False, log_to_mlflow=False)
                
                # 验证集评估
                val_metrics = temp_model.evaluate(val_data, ground_truth=None, verbose=False)
                
                # 获取优化目标分数（越大越好，所以用负数作为 loss）
                score = val_metrics.get(metric, val_metrics.get('template_quality_score', 0))
                loss = -score  # hyperopt 最小化 loss，所以取负数
                
                # 记录到 MLflow
                if mlflow.active_run():
                    # 记录性能指标
                    mlflow.log_metric(f"hyperopt/val_{metric}", score, step=current_eval)
                    mlflow.log_metric("hyperopt/val_num_templates", val_metrics.get('num_templates', 0), step=current_eval)
                    mlflow.log_metric("hyperopt/val_coverage_rate", val_metrics.get('coverage_rate', 0), step=current_eval)
                    mlflow.log_metric("hyperopt/val_template_quality_score", val_metrics.get('template_quality_score', 0), step=current_eval)
                    mlflow.log_metric("hyperopt/success", 1.0, step=current_eval)
                    
                    # 记录参数（同时作为指标，方便可视化）
                    mlflow.log_metric("hyperopt/tau", tau, step=current_eval)
                    mlflow.log_param(f"trial_{current_eval}_tau", tau)
                    
                    if 'merge_threshold' in decoded_params:
                        mlflow.log_metric("hyperopt/merge_threshold", merge_threshold, step=current_eval)
                        mlflow.log_param(f"trial_{current_eval}_merge", merge_threshold)
                    
                    if 'diversity_threshold' in decoded_params:
                        mlflow.log_metric("hyperopt/diversity_threshold", diversity_threshold, step=current_eval)
                        mlflow.log_param(f"trial_{current_eval}_diversity", diversity_threshold)
                
                # 记录最优结果
                if score > best_score[0]:
                    best_score[0] = score
                    logger.info(f"  ✓ 发现更优参数! [{current_eval}/{max_evals}] {metric}={score:.4f}, {param_str}")
                    
                    if mlflow.active_run():
                        mlflow.log_metric("hyperopt/best_so_far", score, step=current_eval)
                
                return {'loss': float(loss), 'status': STATUS_OK}
                
            except Exception as e:
                failed_count[0] += 1
                logger.error(
                    f"  [{current_eval}/{max_evals}] 参数评估失败: {type(e).__name__}: {str(e)}"
                )
                
                if mlflow.active_run():
                    mlflow.log_metric("hyperopt/success", 0.0, step=current_eval)
                    error_msg = str(e)[:150]
                    mlflow.log_param(f"trial_{current_eval}_error", error_msg)
                
                return {'loss': float('inf'), 'status': STATUS_OK}
        
        # 运行优化
        from hyperopt.early_stop import no_progress_loss
        
        best_params_raw = fmin(
            fn=objective,
            space=space,
            algo=tpe.suggest,
            max_evals=max_evals,
            trials=trials,
            early_stop_fn=no_progress_loss(patience) if early_stop_enabled else None,
            rstate=np.random.default_rng(None),
            verbose=False
        )
        
        # 使用 space_eval 将索引转换为实际值
        best_params_actual = space_eval(space, best_params_raw)
        best_params = self._decode_params(best_params_actual, search_space_config)
        
        logger.info(f"超参数优化完成! 最优{metric}: {best_score[0]:.4f}")
        logger.info(f"最优参数: {best_params}")
        
        # 记录优化摘要统计到 MLflow
        if mlflow.active_run():
            success_losses = [
                t['result']['loss'] for t in trials.trials 
                if t['result']['status'] == 'ok' and t['result']['loss'] != float('inf')
            ]
            
            success_count = len(success_losses)
            actual_evals = len(trials.trials)
            is_early_stopped = actual_evals < max_evals
            
            summary_metrics = {
                "hyperopt_summary/total_evals": max_evals,
                "hyperopt_summary/actual_evals": actual_evals,
                "hyperopt_summary/successful_evals": success_count,
                "hyperopt_summary/failed_evals": failed_count[0],
                "hyperopt_summary/success_rate": (success_count / actual_evals * 100) if actual_evals > 0 else 0,
                "hyperopt_summary/best_score": best_score[0],
            }
            
            if early_stop_enabled:
                summary_metrics["hyperopt_summary/early_stop_enabled"] = 1.0
                summary_metrics["hyperopt_summary/early_stopped"] = 1.0 if is_early_stopped else 0.0
                summary_metrics["hyperopt_summary/patience_used"] = patience
                
                if is_early_stopped:
                    time_saved_pct = ((max_evals - actual_evals) / max_evals * 100) if max_evals > 0 else 0
                    summary_metrics["hyperopt_summary/time_saved_pct"] = time_saved_pct
                    logger.info(
                        f"早停统计: 在 {actual_evals}/{max_evals} 次停止, "
                        f"节省 {time_saved_pct:.1f}% 时间"
                    )
            
            if success_losses:
                # 注意：loss 是负数，需要转回正数
                success_scores = [-loss for loss in success_losses]
                summary_metrics.update({
                    "hyperopt_summary/worst_score": min(success_scores),
                    "hyperopt_summary/mean_score": np.mean(success_scores),
                    "hyperopt_summary/median_score": np.median(success_scores),
                    "hyperopt_summary/std_score": np.std(success_scores),
                })
            
            mlflow.log_metrics(summary_metrics)
            logger.info(
                f"优化摘要: 成功率 {summary_metrics['hyperopt_summary/success_rate']:.1f}% "
                f"({success_count}/{actual_evals})"
            )
        
        # 更新当前模型参数
        self.tau = best_params.get('tau', self.tau)
        self.merge_threshold = best_params.get('merge_threshold', self.merge_threshold)
        self.diversity_threshold = best_params.get('diversity_threshold', self.diversity_threshold)
        
        if hasattr(self, 'config'):
            if isinstance(self.config, dict):
                if 'params' not in self.config:
                    self.config['params'] = {}
                self.config['params'].update(best_params)
            else:
                self.config = {'params': best_params}
        
        return best_params
    
    def _build_search_space(self, search_space_config: Dict) -> Dict:
        """构建 Hyperopt 搜索空间
        
        Args:
            search_space_config: 搜索空间配置
            
        Returns:
            Hyperopt 搜索空间字典
        """
        from hyperopt import hp
        
        if not search_space_config:
            # 默认搜索空间：tau 相似度阈值
            return {
                'tau': hp.choice('tau', [0.3, 0.4, 0.5, 0.6, 0.7, 0.8])
            }
        
        # 从配置构建搜索空间
        space = {}
        
        # tau 参数
        if 'tau' in search_space_config:
            tau_values = search_space_config['tau']
            if isinstance(tau_values, list):
                space['tau'] = hp.choice('tau', tau_values)
            elif isinstance(tau_values, dict):
                # 支持 uniform 分布
                if tau_values.get('type') == 'uniform':
                    space['tau'] = hp.uniform('tau', tau_values['low'], tau_values['high'])
                else:
                    space['tau'] = hp.choice('tau', tau_values.get('values', [0.5]))
        
        # merge_threshold 参数
        if 'merge_threshold' in search_space_config:
            merge_values = search_space_config['merge_threshold']
            if isinstance(merge_values, list):
                space['merge_threshold'] = hp.choice('merge_threshold', merge_values)
            elif isinstance(merge_values, dict):
                if merge_values.get('type') == 'uniform':
                    space['merge_threshold'] = hp.uniform('merge_threshold', merge_values['low'], merge_values['high'])
                else:
                    space['merge_threshold'] = hp.choice('merge_threshold', merge_values.get('values', [0.85]))
        
        # diversity_threshold 参数
        if 'diversity_threshold' in search_space_config:
            div_values = search_space_config['diversity_threshold']
            if isinstance(div_values, list):
                space['diversity_threshold'] = hp.choice('diversity_threshold', div_values)
            elif isinstance(div_values, dict):
                if div_values.get('type') == 'quniform':
                    space['diversity_threshold'] = hp.quniform(
                        'diversity_threshold', 
                        div_values['low'], 
                        div_values['high'],
                        div_values.get('q', 1)
                    )
                else:
                    space['diversity_threshold'] = hp.choice('diversity_threshold', div_values.get('values', [3]))
        
        # 如果没有任何配置，使用默认 tau
        if not space:
            space['tau'] = hp.choice('tau', [0.3, 0.4, 0.5, 0.6, 0.7, 0.8])
        
        return space
    
    def _decode_params(self, params_raw: Dict, search_space_config: Dict) -> Dict:
        """解码 Hyperopt 参数
        
        Args:
            params_raw: Hyperopt 返回的参数（经过 space_eval 转换后的实际值）
            search_space_config: 搜索空间配置（未使用，保留接口兼容性）
            
        Returns:
            解码后的参数字典
        """
        import numpy as np
        
        # 转换 numpy 类型为 Python 原生类型
        decoded = {}
        for key, value in params_raw.items():
            if isinstance(value, np.floating):
                decoded[key] = float(value)
            elif isinstance(value, np.integer):
                decoded[key] = int(value)
            else:
                decoded[key] = value
        
        # 参数验证和修正
        if 'tau' in decoded:
            tau = decoded['tau']
            # tau 范围应该在 (0, 1]，通常建议 0.3-0.8
            if not 0 < tau <= 1.0:
                logger.warning(
                    f"tau={tau} 超出有效范围 (0, 1.0]，已修正为 0.5"
                )
                decoded['tau'] = 0.5
        
        if 'merge_threshold' in decoded:
            merge = decoded['merge_threshold']
            # merge_threshold 范围应该在 (0, 1]
            if not 0 < merge <= 1.0:
                logger.warning(
                    f"merge_threshold={merge} 超出有效范围 (0, 1.0]，已修正为 0.85"
                )
                decoded['merge_threshold'] = 0.85
        
        if 'diversity_threshold' in decoded:
            diversity = decoded['diversity_threshold']
            # diversity_threshold 应该是正整数
            if diversity < 1:
                logger.warning(
                    f"diversity_threshold={diversity} 小于 1，已修正为 3"
                )
                decoded['diversity_threshold'] = 3
            else:
                decoded['diversity_threshold'] = int(diversity)
        
        return decoded
    
    # ==================== 核心辅助方法 ====================
    
    def _tokenize(self, log: str) -> List[str]:
        """Token 化日志
        
        Args:
            log: 日志字符串
            
        Returns:
            Token 列表
        """
        # 简单策略：按空格分割
        return log.split()
    
    def _compute_lcs(self, seq1: List[str], seq2: List[str]) -> List[str]:
        """计算最长公共子序列（LCS）
        
        Args:
            seq1: 序列1
            seq2: 序列2
            
        Returns:
            LCS 序列
        """
        # 检查缓存
        if self.lcs_cache is not None:
            key = (tuple(seq1), tuple(seq2))
            if key in self.lcs_cache:
                return self.lcs_cache[key]
        
        # 动态规划计算 LCS
        m, n = len(seq1), len(seq2)
        dp = [[0] * (n + 1) for _ in range(m + 1)]
        
        for i in range(1, m + 1):
            for j in range(1, n + 1):
                if seq1[i-1] == seq2[j-1]:
                    dp[i][j] = dp[i-1][j-1] + 1
                else:
                    dp[i][j] = max(dp[i-1][j], dp[i][j-1])
        
        # 回溯构建 LCS
        lcs = []
        i, j = m, n
        while i > 0 and j > 0:
            if seq1[i-1] == seq2[j-1]:
                lcs.insert(0, seq1[i-1])
                i -= 1
                j -= 1
            elif dp[i-1][j] > dp[i][j-1]:
                i -= 1
            else:
                j -= 1
        
        # 更新缓存
        if self.lcs_cache is not None and len(self.lcs_cache) < 5000:
            key = (tuple(seq1), tuple(seq2))
            self.lcs_cache[key] = lcs
        
        return lcs
    
    def _get_position_weight(self, position: int, length: int) -> float:
        """获取位置权重
        
        Args:
            position: Token 位置（0-based）
            length: 序列总长度
            
        Returns:
            位置权重
        """
        if not self.use_position_weight:
            return 1.0
        
        cfg = self.position_weight_config
        
        # 前 N 个 token（头部）
        if position < cfg['head_count']:
            return cfg['head_weight']
        
        # 后 N 个 token（尾部）
        if position >= length - cfg['tail_count']:
            return cfg['tail_weight']
        
        # 中间部分
        return cfg['middle_weight']
    
    def _lcs_similarity(self, seq1: List[str], seq2: List[str]) -> float:
        """计算 LCS 相似度（带位置权重）
        
        Args:
            seq1: 序列1
            seq2: 序列2
            
        Returns:
            相似度得分 [0, 1]
        """
        if not seq1 or not seq2:
            return 0.0
        
        lcs = self._compute_lcs(seq1, seq2)
        
        if not self.use_position_weight:
            # 标准 LCS 相似度
            return len(lcs) / len(seq1)
        
        # 位置加权相似度
        lcs_set = set(lcs)
        total_weight = 0.0
        max_weight = 0.0
        
        for i, token in enumerate(seq1):
            weight = self._get_position_weight(i, len(seq1))
            max_weight += weight
            if token in lcs_set:
                total_weight += weight
        
        return total_weight / max_weight if max_weight > 0 else 0.0
    
    def _quick_filter(self, seq: List[str], template: List[str]) -> bool:
        """快速过滤不可能匹配的聚类
        
        Args:
            seq: 日志序列
            template: 模板序列
            
        Returns:
            True 表示可能匹配，False 表示肯定不匹配
        """
        # 长度过滤
        len_ratio = len(seq) / len(template) if template else 0
        if len_ratio < 0.5 or len_ratio > 2.0:
            return False
        
        # Token 交集过滤
        seq_set = set(seq) - {'<*>'}
        template_set = set(template) - {'<*>'}
        
        if not seq_set or not template_set:
            return True
        
        overlap = len(seq_set & template_set)
        min_len = min(len(seq_set), len(template_set))
        
        if overlap / min_len < 0.3:
            return False
        
        # 首尾 token 检查（运维日志特点）
        if seq[0] != template[0] and template[0] != '<*>':
            return False
        if seq[-1] != template[-1] and template[-1] != '<*>':
            return False
        
        return True
    
    def _update_template(self, logs: List[List[str]]) -> List[str]:
        """使用多数投票更新模板
        
        Args:
            logs: 日志 token 序列列表
            
        Returns:
            更新后的模板
        """
        if not logs:
            return []
        
        if len(logs) == 1:
            return logs[0]
        
        # 计算 LCS 作为基础模板
        template = logs[0]
        for log in logs[1:]:
            template = self._compute_lcs(template, log)
        
        # 多数投票：对每个位置，统计最常见的 token
        max_len = max(len(log) for log in logs)
        voted_template = []
        
        for pos in range(max_len):
            token_counts = Counter()
            for log in logs:
                if pos < len(log):
                    token_counts[log[pos]] += 1
            
            if token_counts:
                # 检查多样性阈值
                most_common_token, count = token_counts.most_common(1)[0]
                diversity = len(token_counts)
                
                if diversity >= self.diversity_threshold:
                    # Token 变化过多，标记为通配符
                    voted_template.append('<*>')
                else:
                    # 使用多数票 token
                    voted_template.append(most_common_token)
        
        return voted_template
    
    def _merge_clusters(self):
        """合并相似的聚类
        
        使用贪心策略：按聚类大小降序，依次尝试合并到已有聚类。
        """
        if len(self.clusters) <= 1:
            return
        
        # 按聚类大小排序（大聚类优先保留）
        sorted_clusters = sorted(
            enumerate(self.clusters),
            key=lambda x: len(x[1]['log_ids']),
            reverse=True
        )
        
        merged = [False] * len(self.clusters)
        new_clusters = []
        
        for old_idx, cluster in sorted_clusters:
            if merged[old_idx]:
                continue
            
            # 尝试合并到已有的新聚类
            merged_to = -1
            best_sim = 0.0
            
            for new_idx, new_cluster in enumerate(new_clusters):
                sim = self._lcs_similarity(cluster['template'], new_cluster['template'])
                if sim >= self.merge_threshold and sim > best_sim:
                    best_sim = sim
                    merged_to = new_idx
            
            if merged_to >= 0:
                # 合并到现有聚类
                target = new_clusters[merged_to]
                target['logs'].extend(cluster['logs'])
                target['log_ids'].extend(cluster['log_ids'])
                target['template'] = self._update_template(target['logs'])
                merged[old_idx] = True
            else:
                # 创建新聚类
                new_cluster = {
                    'id': len(new_clusters),
                    'template': cluster['template'],
                    'logs': cluster['logs'],
                    'log_ids': cluster['log_ids'],
                }
                new_clusters.append(new_cluster)
        
        # 更新聚类列表
        self.clusters = new_clusters
        
        # 重建倒排索引
        self.token_index = defaultdict(set)
        for cluster_id, cluster in enumerate(self.clusters):
            for token in cluster['template']:
                if token != '<*>':
                    self.token_index[token].add(cluster_id)
    
    # ==================== 可解释性方法 ====================
    
    def explain_prediction(self, log: str, cluster_id: Optional[int] = None) -> Dict[str, Any]:
        """解释单个日志的预测结果
        
        Args:
            log: 日志字符串
            cluster_id: 可选的聚类 ID，如果提供则解释与该聚类的匹配；
                       否则自动预测并解释
        
        Returns:
            解释信息字典，包含：
            - log: 原始日志
            - cluster_id: 匹配的聚类 ID（-1 表示未匹配）
            - template: 匹配的模板
            - similarity: 相似度得分
            - matched_tokens: 匹配的 token 列表
            - unmatched_tokens: 不匹配的 token 列表
            - position_weights: 位置权重信息（如果启用）
            - match_details: 详细匹配信息（字段格式）
        
        Raises:
            RuntimeError: 模型未训练
        """
        self._check_fitted()
        
        tokens = self._tokenize(log)
        
        if not tokens:
            return {
                'log': log,
                'cluster_id': -1,
                'template': None,
                'similarity': 0.0,
                'matched_tokens': [],
                'unmatched_tokens': [],
                'match_details': "空日志，无法匹配"
            }
        
        # 如果未提供 cluster_id，自动预测
        if cluster_id is None:
            predictions = self.predict([log])
            cluster_id = predictions[0]
        
        # 未匹配
        if cluster_id == -1 or cluster_id >= len(self.clusters):
            return {
                'log': log,
                'cluster_id': -1,
                'template': None,
                'similarity': 0.0,
                'matched_tokens': [],
                'unmatched_tokens': tokens,
                'match_details': "未找到匹配的聚类"
            }
        
        # 获取聚类信息
        cluster = self.clusters[cluster_id]
        template = cluster['template']
        template_str = ' '.join(template)
        
        # 计算相似度和匹配详情
        similarity = self._lcs_similarity(tokens, template)
        lcs = self._compute_lcs(tokens, template)
        lcs_set = set(lcs)
        
        # 分析匹配和不匹配的 token
        matched_tokens = []
        unmatched_tokens = []
        
        for token in tokens:
            if token in lcs_set:
                matched_tokens.append(token)
            else:
                unmatched_tokens.append(token)
        
        # 构建字段格式输出
        match_details = self._format_match_details(tokens, template, lcs_set)
        
        # 位置权重信息（如果启用）
        position_weights = None
        if self.use_position_weight:
            position_weights = [
                {
                    'position': i,
                    'token': token,
                    'weight': self._get_position_weight(i, len(tokens))
                }
                for i, token in enumerate(tokens)
            ]
        
        explanation = {
            'log': log,
            'cluster_id': cluster_id,
            'template': template_str,
            'similarity': similarity,
            'matched_tokens': matched_tokens,
            'unmatched_tokens': unmatched_tokens,
            'match_details': match_details,
        }
        
        if position_weights:
            explanation['position_weights'] = position_weights
        
        return explanation
    
    def _format_match_details(
        self, 
        tokens: List[str], 
        template: List[str], 
        lcs_set: Set[str]
    ) -> str:
        """格式化匹配详情为字段格式输出
        
        Args:
            tokens: 日志 token 列表
            template: 模板 token 列表
            lcs_set: LCS token 集合
        
        Returns:
            格式化的匹配详情字符串
        """
        lines = []
        lines.append("匹配详情:")
        lines.append(f"  日志:   {' '.join(tokens)}")
        lines.append(f"  模板:   {' '.join(template)}")
        
        # 标记匹配状态
        match_markers = []
        for token in tokens:
            if token in lcs_set:
                match_markers.append('✓')
            else:
                match_markers.append('✗')
        
        lines.append(f"  匹配:   {' '.join(match_markers)}")
        
        # Token 对齐显示（如果长度相同）
        if len(tokens) == len(template):
            lines.append("\nToken 对齐:")
            for i, (log_token, tpl_token) in enumerate(zip(tokens, template)):
                marker = '✓' if log_token in lcs_set else '✗'
                if log_token == tpl_token:
                    lines.append(f"  [{i}] {marker} {log_token} == {tpl_token}")
                elif tpl_token == '<*>':
                    lines.append(f"  [{i}] {marker} {log_token} => <*> (通配符)")
                else:
                    lines.append(f"  [{i}] {marker} {log_token} != {tpl_token}")
        
        return '\n'.join(lines)
    
    def get_cluster_summary(self, cluster_id: int, top_logs: int = 5) -> Dict[str, Any]:
        """获取聚类摘要信息
        
        Args:
            cluster_id: 聚类 ID
            top_logs: 返回的代表性日志数量
        
        Returns:
            聚类摘要字典，包含：
            - cluster_id: 聚类 ID
            - template: 模板字符串
            - size: 聚类大小（日志数量）
            - log_ids: 日志索引列表
            - representative_logs: 代表性日志列表（原始格式）
            - template_tokens: 模板 token 列表
            - wildcard_count: 通配符数量
            - avg_log_length: 平均日志长度
        
        Raises:
            RuntimeError: 模型未训练
            ValueError: 无效的聚类 ID
        """
        self._check_fitted()
        
        if cluster_id < 0 or cluster_id >= len(self.clusters):
            raise ValueError(f"无效的聚类 ID: {cluster_id}")
        
        cluster = self.clusters[cluster_id]
        template = cluster['template']
        log_ids = cluster['log_ids']
        
        # 获取代表性日志
        representative_logs = []
        if self.enable_explain and self.raw_logs:
            sample_size = min(top_logs, len(log_ids))
            sample_indices = log_ids[:sample_size]
            
            for idx in sample_indices:
                if idx < len(self.raw_logs):
                    representative_logs.append(self.raw_logs[idx])
        
        # 统计信息
        wildcard_count = sum(1 for token in template if token == '<*>')
        
        avg_log_length = 0.0
        if cluster['logs']:
            total_length = sum(len(log) for log in cluster['logs'])
            avg_log_length = total_length / len(cluster['logs'])
        
        summary = {
            'cluster_id': cluster_id,
            'template': ' '.join(template),
            'size': len(log_ids),
            'log_ids': log_ids,
            'representative_logs': representative_logs,
            'template_tokens': template,
            'wildcard_count': wildcard_count,
            'avg_log_length': avg_log_length,
        }
        
        return summary
    
    def get_match_details(
        self, 
        log: str, 
        cluster_id: int
    ) -> Dict[str, Any]:
        """获取日志与聚类的详细匹配信息
        
        Args:
            log: 日志字符串
            cluster_id: 聚类 ID
        
        Returns:
            匹配详情字典，包含：
            - log: 原始日志
            - cluster_id: 聚类 ID
            - template: 模板字符串
            - similarity: 相似度得分
            - lcs: LCS 序列
            - lcs_length: LCS 长度
            - log_length: 日志长度
            - template_length: 模板长度
            - token_alignment: Token 对齐信息
        
        Raises:
            RuntimeError: 模型未训练
            ValueError: 无效的聚类 ID
        """
        self._check_fitted()
        
        if cluster_id < 0 or cluster_id >= len(self.clusters):
            raise ValueError(f"无效的聚类 ID: {cluster_id}")
        
        tokens = self._tokenize(log)
        cluster = self.clusters[cluster_id]
        template = cluster['template']
        
        # 计算 LCS 和相似度
        lcs = self._compute_lcs(tokens, template)
        similarity = self._lcs_similarity(tokens, template)
        
        # Token 对齐信息
        token_alignment = []
        max_len = max(len(tokens), len(template))
        
        for i in range(max_len):
            log_token = tokens[i] if i < len(tokens) else None
            tpl_token = template[i] if i < len(template) else None
            
            is_match = False
            if log_token and tpl_token:
                if log_token == tpl_token:
                    is_match = True
                elif tpl_token == '<*>':
                    is_match = True  # 通配符匹配
            
            token_alignment.append({
                'position': i,
                'log_token': log_token,
                'template_token': tpl_token,
                'is_match': is_match,
                'weight': self._get_position_weight(i, len(tokens)) if log_token else 0.0
            })
        
        details = {
            'log': log,
            'cluster_id': cluster_id,
            'template': ' '.join(template),
            'similarity': similarity,
            'lcs': lcs,
            'lcs_length': len(lcs),
            'log_length': len(tokens),
            'template_length': len(template),
            'token_alignment': token_alignment,
        }
        
        return details
