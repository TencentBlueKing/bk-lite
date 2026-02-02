#!/bin/bash
# BentoML Serving API 测试脚本

BASE_URL="http://localhost:3000"

echo "=== 测试健康检查 ==="
curl -X POST "${BASE_URL}/health" && echo

echo -e "\n=== 测试预测接口 (Dummy Model) ==="
curl -X POST "${BASE_URL}/predict" \
  -H "Content-Type: application/json" \
  -d '{"request": {"features": {"feature1": 1.0, "feature2": 2.5, "feature3": 0.8}}}' && echo

echo -e "\n=== 测试预测接口 (不同数据) ==="
curl -X POST "${BASE_URL}/predict" \
  -H "Content-Type: application/json" \
  -d '{"request": {"features": {"age": 25, "income": 50000, "score": 0.85}}}' && echo