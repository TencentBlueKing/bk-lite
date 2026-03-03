#!/bin/bash
# BentoML Serving API 测试脚本

BASE_URL="http://localhost:3000"

echo "=== 测试健康检查 ==="
curl -X POST "${BASE_URL}/health" && echo

echo -e "\n=== 测试日志聚类接口 (单条日志) ==="
curl -X POST "${BASE_URL}/cluster_logs" \
  -H "Content-Type: application/json" \
  -d '{
    "logs": [
      "User login failed from IP 192.168.1.100"
    ]
  }' && echo

echo -e "\n=== 测试日志聚类接口 (批量日志) ==="
curl -X POST "${BASE_URL}/cluster_logs" \
  -H "Content-Type: application/json" \
  -d '{
    "logs": [
      "User login failed from IP 192.168.1.100",
      "Database connection timeout after 30 seconds",
      "User login failed from IP 10.0.0.5",
      "Failed to connect to database server at 192.168.1.200",
      "User admin logged in successfully",
      "Database connection timeout after 30 seconds",
      "API request failed with status code 500",
      "Memory usage exceeded 90% threshold",
      "User login failed from IP 172.16.0.10"
    ]
  }' && echo

echo -e "\n=== 测试结果说明 ==="
echo "响应字段："
echo "  - results: 每条日志的聚类结果列表"
echo "    - log: 原始日志消息"
echo "    - cluster_id: 聚类 ID (模板 ID)"
echo "    - template: 对应的日志模板"
echo "  - num_templates: 发现的模板总数"
echo "  - model_version: 模型版本"
echo "  - source: 模型来源 (local/mlflow/dummy)"

echo -e "\n=== 测试预测接口 (Dummy Model) ==="
curl -X POST "${BASE_URL}/predict" \
  -H "Content-Type: application/json" \
  -d '{"request": {"features": {"feature1": 1.0, "feature2": 2.5, "feature3": 0.8}}}' && echo

echo -e "\n=== 测试预测接口 (不同数据) ==="
curl -X POST "${BASE_URL}/predict" \
  -H "Content-Type: application/json" \
  -d '{"request": {"features": {"age": 25, "income": 50000, "score": 0.85}}}' && echo