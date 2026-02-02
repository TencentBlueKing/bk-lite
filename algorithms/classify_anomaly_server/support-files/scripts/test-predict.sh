#!/bin/bash
# BentoML Serving API 测试脚本

BASE_URL="http://localhost:3000"

echo "=== 测试健康检查 ==="
curl -X POST "${BASE_URL}/health" && echo

echo -e "\n=== 测试异常检测接口 (单条时间序列) ==="
curl -X POST "${BASE_URL}/detect" \
  -H "Content-Type: application/json" \
  -d '{
    "request": {
      "features": {
        "timestamp": "2024-01-01 00:00:00",
        "value": 125.5,
        "rolling_mean_12": 120.3,
        "rolling_std_12": 5.2,
        "lag_1": 118.9,
        "hour": 0,
        "day_of_week": 0
      }
    }
  }' && echo

echo -e "\n=== 测试批量异常检测接口 ==="
curl -X POST "${BASE_URL}/detect_batch" \
  -H "Content-Type: application/json" \
  -d '{
    "request": {
      "data": [
        {
          "timestamp": "2024-01-01 00:00:00",
          "value": 125.5,
          "rolling_mean_12": 120.3,
          "rolling_std_12": 5.2
        },
        {
          "timestamp": "2024-01-01 01:00:00",
          "value": 230.8,
          "rolling_mean_12": 122.1,
          "rolling_std_12": 8.5
        }
      ]
    }
  }' && echo