#!/bin/bash
# 目标检测服务 API 测试脚本

BASE_URL="${BASE_URL:-http://localhost:3000}"

echo "=== 测试健康检查 ==="
curl -X POST "${BASE_URL}/health" && echo

echo -e "\n=== 测试预测接口 (单张图片) ==="
# 需要准备一张测试图片，这里使用 base64 编码
# 如果有实际图片文件，可以使用: base64 -w 0 test_image.jpg

# 示例：使用一个最小的1x1像素PNG图片的base64编码进行测试
TEST_IMAGE_BASE64="iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNk+M9QDwADhgGAWjR9awAAAABJRU5ErkJggg=="

curl -X POST "${BASE_URL}/predict" \
  -H "Content-Type: application/json" \
  -d "{\"images\": [\"${TEST_IMAGE_BASE64}\"], \"config\": {\"conf_threshold\": 0.25}}" && echo

echo -e "\n=== 测试预测接口 (批量图片) ==="
curl -X POST "${BASE_URL}/predict" \
  -H "Content-Type: application/json" \
  -d "{\"images\": [\"${TEST_IMAGE_BASE64}\", \"${TEST_IMAGE_BASE64}\"], \"config\": {\"conf_threshold\": 0.5, \"iou_threshold\": 0.45}}" && echo

echo -e "\n提示: 要测试真实图片，请使用以下命令生成 base64 编码："
echo "  Linux/Mac: base64 -w 0 image.jpg"
echo "  Windows (PowerShell): [Convert]::ToBase64String([IO.File]::ReadAllBytes('image.jpg'))"