#!/bin/bash
# Feishu Webhook Bot API Examples using CURL
# Replace your_webhook_token with actual token

WEBHOOK_URL="https://open.feishu.cn/open-apis/bot/v2/hook/your_webhook_token"

# =============================================================================
# EXAMPLE 1: Send Simple Text Message
# =============================================================================
echo "Example 1: Send text message"
curl -X POST "$WEBHOOK_URL" \
  -H 'Content-Type: application/json' \
  -d '{
    "msg_type": "text",
    "content": {
      "text": "Hello from Feishu Bot!"
    }
  }'
echo -e "\n"

# =============================================================================
# EXAMPLE 2: Send Markdown/Rich Text Message
# =============================================================================
echo "Example 2: Send markdown message with link"
curl -X POST "$WEBHOOK_URL" \
  -H 'Content-Type: application/json' \
  -d '{
    "msg_type": "post",
    "content": {
      "post": {
        "zh_cn": {
          "title": "System Notification",
          "content": [
            [
              {
                "tag": "text",
                "text": "Server status: "
              },
              {
                "tag": "a",
                "text": "Check Dashboard",
                "href": "https://example.com/dashboard"
              }
            ]
          ]
        }
      }
    }
  }'
echo -e "\n"

# =============================================================================
# EXAMPLE 3: Send Interactive Card with Button
# =============================================================================
echo "Example 3: Send interactive card"
curl -X POST "$WEBHOOK_URL" \
  -H 'Content-Type: application/json' \
  -d '{
    "msg_type": "interactive",
    "card": {
      "config": {
        "wide_screen_mode": true,
        "enable_forward": true
      },
      "header": {
        "title": {
          "content": "Deployment Notification",
          "tag": "plain_text"
        },
        "template": "blue"
      },
      "elements": [
        {
          "tag": "markdown",
          "content": "**Project**: Backend API\n**Status**: Deployed\n**Version**: v2.1.0"
        },
        {
          "tag": "button",
          "text": {
            "content": "View Deployment",
            "tag": "plain_text"
          },
          "type": "primary",
          "action": {
            "type": "open_url",
            "url": "https://example.com/deployments/123"
          }
        }
      ]
    }
  }'
echo -e "\n"

# =============================================================================
# EXAMPLE 4: Send Card with Multiple Elements
# =============================================================================
echo "Example 4: Send advanced card with multiple elements"
curl -X POST "$WEBHOOK_URL" \
  -H 'Content-Type: application/json' \
  -d '{
    "msg_type": "interactive",
    "card": {
      "config": {
        "wide_screen_mode": true
      },
      "header": {
        "title": {
          "content": "Build Report",
          "tag": "plain_text"
        },
        "template": "green"
      },
      "elements": [
        {
          "tag": "markdown",
          "content": "**Build Status**: ✅ Success\n**Build Number**: #542\n**Duration**: 5m 23s"
        },
        {
          "tag": "divider"
        },
        {
          "tag": "markdown",
          "content": "**Test Results**\n- Total Tests: 450\n- Passed: 450\n- Failed: 0\n- Coverage: 95%"
        },
        {
          "tag": "button",
          "text": {
            "content": "View Build Details",
            "tag": "plain_text"
          },
          "type": "primary",
          "action": {
            "type": "open_url",
            "url": "https://example.com/builds/542"
          }
        }
      ]
    }
  }'
echo -e "\n"

# =============================================================================
# EXAMPLE 5: Send Card with Red Template (Error)
# =============================================================================
echo "Example 5: Send error notification card"
curl -X POST "$WEBHOOK_URL" \
  -H 'Content-Type: application/json' \
  -d '{
    "msg_type": "interactive",
    "card": {
      "header": {
        "title": {
          "content": "Alert: System Error",
          "tag": "plain_text"
        },
        "template": "red"
      },
      "elements": [
        {
          "tag": "markdown",
          "content": "**Service**: Payment Gateway\n**Error**: Database Connection Failed\n**Time**: 2025-02-26 10:30:00"
        }
      ]
    }
  }'
echo -e "\n"

# =============================================================================
# EXAMPLE 6: Send Card with Multiple Actions
# =============================================================================
echo "Example 6: Send card with multiple buttons"
curl -X POST "$WEBHOOK_URL" \
  -H 'Content-Type: application/json' \
  -d '{
    "msg_type": "interactive",
    "card": {
      "header": {
        "title": {
          "content": "Code Review Request",
          "tag": "plain_text"
        },
        "template": "purple"
      },
      "elements": [
        {
          "tag": "markdown",
          "content": "**PR**: Feature: Add payment API\n**Author**: John Doe\n**Branch**: feature/payment-api"
        },
        {
          "tag": "button",
          "text": {
            "content": "View Pull Request",
            "tag": "plain_text"
          },
          "type": "primary",
          "action": {
            "type": "open_url",
            "url": "https://github.com/example/repo/pull/123"
          }
        },
        {
          "tag": "button",
          "text": {
            "content": "Open in IDE",
            "tag": "plain_text"
          },
          "type": "default",
          "action": {
            "type": "open_url",
            "url": "vscode://github.com/example/repo/pull/123"
          }
        }
      ]
    }
  }'
echo -e "\n"

# =============================================================================
# EXAMPLE 7: Send Message with Signature Verification
# =============================================================================
echo "Example 7: Send message with signature"

# Calculate timestamp and signature
TIMESTAMP=$(date +%s)
SECRET_KEY="your_secret_key"
SIGNATURE_STRING="${TIMESTAMP}
${SECRET_KEY}"

# Calculate HMAC-SHA256 and base64 encode
SIGNATURE=$(echo -n "" | openssl dgst -sha256 -hmac "$SIGNATURE_STRING" -binary | base64)

curl -X POST "$WEBHOOK_URL" \
  -H 'Content-Type: application/json' \
  -d '{
    "msg_type": "text",
    "content": {
      "text": "Signed message from server"
    },
    "timestamp": "'$TIMESTAMP'",
    "sign": "'$SIGNATURE'"
  }'
echo -e "\n"

# =============================================================================
# EXAMPLE 8: Test Webhook with Simple GET Request Status
# =============================================================================
echo "Example 8: Test webhook connectivity"
curl -I -X POST "$WEBHOOK_URL" \
  -H 'Content-Type: application/json'
echo -e "\n"

# =============================================================================
# FUNCTION: Generic Send Message Function
# =============================================================================
send_feishu_message() {
    local msg_type=$1
    local json_content=$2
    
    curl -X POST "$WEBHOOK_URL" \
        -H 'Content-Type: application/json' \
        -d '{
            "msg_type": "'$msg_type'",
            "content": '$json_content'
        }'
}

# Usage examples:
# send_feishu_message "text" '{"text": "Hello"}'
# send_feishu_message "image" '{"image_key": "img_xxx"}'

