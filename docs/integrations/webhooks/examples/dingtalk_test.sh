#!/bin/bash
# DingTalk Webhook Bot - Testing & Validation Script
# This script helps test your DingTalk webhook bot configuration

set -e

# Color codes for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

echo -e "${BLUE}═══════════════════════════════════════════════════════${NC}"
echo -e "${BLUE}DingTalk Webhook Bot - Test & Validation Script${NC}"
echo -e "${BLUE}═══════════════════════════════════════════════════════${NC}\n"

# Function to print section headers
print_header() {
    echo -e "\n${BLUE}▶ $1${NC}\n"
}

# Function to print success
print_success() {
    echo -e "${GREEN}✓ $1${NC}"
}

# Function to print error
print_error() {
    echo -e "${RED}✗ $1${NC}"
}

# Function to print warning
print_warning() {
    echo -e "${YELLOW}⚠ $1${NC}"
}

# Function to print info
print_info() {
    echo -e "${BLUE}ℹ $1${NC}"
}

# Check required tools
print_header "Checking Required Tools"

REQUIRED_TOOLS=("curl" "jq" "openssl")
MISSING_TOOLS=()

for tool in "${REQUIRED_TOOLS[@]}"; do
    if command -v "$tool" &> /dev/null; then
        print_success "$tool is installed"
    else
        print_error "$tool is NOT installed"
        MISSING_TOOLS+=("$tool")
    fi
done

if [ ${#MISSING_TOOLS[@]} -ne 0 ]; then
    print_warning "Some tools are missing. Install them:"
    echo "  Ubuntu/Debian: sudo apt-get install ${MISSING_TOOLS[*]}"
    echo "  macOS: brew install ${MISSING_TOOLS[*]}"
    echo ""
fi

# Check environment variables
print_header "Checking Environment Variables"

if [ -z "$DINGTALK_WEBHOOK_URL" ]; then
    print_error "DINGTALK_WEBHOOK_URL not set"
    echo ""
    echo "Set it with:"
    echo "  export DINGTALK_WEBHOOK_URL='https://oapi.dingtalk.com/robot/send?access_token=YOUR_TOKEN'"
    exit 1
else
    print_success "DINGTALK_WEBHOOK_URL is set"
    echo "  URL: ${DINGTALK_WEBHOOK_URL:0:80}..."
fi

if [ -z "$DINGTALK_SECRET" ]; then
    print_warning "DINGTALK_SECRET not set (using keyword-based security)"
    USE_SIGNATURE=false
else
    print_success "DINGTALK_SECRET is set"
    print_info "Using HMAC-SHA256 signature authentication"
    USE_SIGNATURE=true
fi

# Function to generate signature
generate_signature() {
    local secret=$1
    local timestamp=$(date +%s%N | cut -b1-13)
    
    # Create string to sign
    local string_to_sign="${timestamp}\n${secret}"
    
    # Generate HMAC-SHA256 signature
    local sign=$(echo -ne "$string_to_sign" | openssl dgst -sha256 -hmac "$secret" -binary | base64 | python3 -c "import urllib.parse, sys; print(urllib.parse.quote(sys.stdin.read().strip()))")
    
    echo "$timestamp|$sign"
}

# Function to get final webhook URL
get_webhook_url() {
    if [ "$USE_SIGNATURE" = true ]; then
        local result=$(generate_signature "$DINGTALK_SECRET")
        local timestamp=$(echo "$result" | cut -d'|' -f1)
        local sign=$(echo "$result" | cut -d'|' -f2)
        echo "${DINGTALK_WEBHOOK_URL}&timestamp=${timestamp}&sign=${sign}"
    else
        echo "$DINGTALK_WEBHOOK_URL"
    fi
}

# Function to send test message
send_message() {
    local msg_type=$1
    local payload=$2
    local description=$3
    
    print_info "Sending: $description"
    
    local url=$(get_webhook_url)
    
    # Send request and capture response
    local response=$(curl -s -X POST "$url" \
        -H "Content-Type: application/json;charset=utf-8" \
        -d "$payload" \
        -w "\n%{http_code}")
    
    # Extract HTTP code (last line)
    local http_code=$(echo "$response" | tail -n1)
    
    # Extract response body (everything except last line)
    local body=$(echo "$response" | sed '$d')
    
    # Check response
    if echo "$body" | jq . &> /dev/null; then
        local errcode=$(echo "$body" | jq -r '.errcode // 0')
        local errmsg=$(echo "$body" | jq -r '.errmsg // ""')
        
        if [ "$errcode" = "0" ]; then
            print_success "Message sent successfully (HTTP $http_code)"
            echo "  Response: $errmsg"
            return 0
        else
            print_error "API returned error code: $errcode (HTTP $http_code)"
            echo "  Message: $errmsg"
            return 1
        fi
    else
        print_error "Invalid JSON response (HTTP $http_code)"
        echo "  Response: $body"
        return 1
    fi
}

# Test 1: Simple text message
print_header "Test 1: Simple Text Message"

TIMESTAMP=$(date '+%Y-%m-%d %H:%M:%S')
payload=$(cat <<EOF
{
  "msgtype": "text",
  "text": {
    "content": "DingTalk Bot Test - Text Message\\nTimestamp: $TIMESTAMP"
  }
}
EOF
)

send_message "text" "$payload" "Simple text message"
TEST1_RESULT=$?

# Test 2: Markdown message
print_header "Test 2: Markdown Message"

payload=$(cat <<'EOF'
{
  "msgtype": "markdown",
  "markdown": {
    "title": "DingTalk Bot Test",
    "text": "#### Bot Test Report\n\n> Test Type: Markdown Message\n> Status: Testing\n> Timestamp: %TIMESTAMP%\n\n**Key Information**:\n- API: Working\n- Format: Markdown\n- Encoding: UTF-8"
  }
}
EOF
)

# Replace timestamp placeholder
payload=${payload//%TIMESTAMP%/$TIMESTAMP}

send_message "markdown" "$payload" "Markdown message with formatting"
TEST2_RESULT=$?

# Test 3: Link message
print_header "Test 3: Link Message"

payload=$(cat <<EOF
{
  "msgtype": "link",
  "link": {
    "messageUrl": "https://github.com",
    "title": "GitHub Repository",
    "text": "DingTalk Webhook Bot Test - View our repository",
    "picUrl": "https://github.githubassets.com/images/modules/logos_page/GitHub-Mark.png"
  }
}
EOF
)

send_message "link" "$payload" "Link message"
TEST3_RESULT=$?

# Test 4: @Mention (if phone numbers available)
print_header "Test 4: Message with @Mention"

if [ -z "$TEST_PHONE_NUMBERS" ]; then
    print_warning "TEST_PHONE_NUMBERS not set, skipping @mention test"
    print_info "To test @mentions, set: export TEST_PHONE_NUMBERS='[\"13900000000\"]'"
    TEST4_RESULT=2
else
    payload=$(cat <<EOF
{
  "msgtype": "text",
  "text": {
    "content": "Test message with @mention"
  },
  "at": {
    "atMobiles": $TEST_PHONE_NUMBERS,
    "isAtAll": false
  }
}
EOF
    )
    
    send_message "text" "$payload" "Message with @mention"
    TEST4_RESULT=$?
fi

# Performance test
print_header "Test 5: Response Time"

url=$(get_webhook_url)
payload='{"msgtype":"text","text":{"content":"Performance test"}}'

print_info "Measuring API response time..."

response_time=$( { time curl -s -X POST "$url" \
    -H "Content-Type: application/json;charset=utf-8" \
    -d "$payload" \
    > /dev/null 2>&1; } 2>&1 | grep real | awk '{print $2}')

if [ -n "$response_time" ]; then
    print_success "Response time: $response_time"
    TEST5_RESULT=0
else
    print_error "Could not measure response time"
    TEST5_RESULT=1
fi

# Configuration validation
print_header "Configuration Validation"

# Check webhook URL format
if [[ "$DINGTALK_WEBHOOK_URL" =~ ^https://oapi.dingtalk.com/robot/send ]]; then
    print_success "Webhook URL format is correct"
else
    print_error "Invalid webhook URL format"
fi

# Check access token format
if [[ "$DINGTALK_WEBHOOK_URL" =~ access_token=([a-zA-Z0-9]+) ]]; then
    print_success "Access token is present in URL"
else
    print_error "No access token found in URL"
fi

# Check secret format (if configured)
if [ "$USE_SIGNATURE" = true ]; then
    if [[ "$DINGTALK_SECRET" =~ ^SEC[a-zA-Z0-9]{20,} ]]; then
        print_success "Secret token format looks correct (starts with SEC)"
    else
        print_warning "Secret token format may be incorrect (should start with SEC)"
    fi
fi

# Summary
print_header "Test Summary"

TOTAL_TESTS=5
PASSED_TESTS=0

declare -A TEST_RESULTS=( [1]=$TEST1_RESULT [2]=$TEST2_RESULT [3]=$TEST3_RESULT [4]=$TEST4_RESULT [5]=$TEST5_RESULT )

for test_num in "${!TEST_RESULTS[@]}"; do
    case "${TEST_RESULTS[$test_num]}" in
        0)
            echo -e "  Test $test_num: ${GREEN}PASSED${NC}"
            ((PASSED_TESTS++))
            ;;
        1)
            echo -e "  Test $test_num: ${RED}FAILED${NC}"
            ;;
        2)
            echo -e "  Test $test_num: ${YELLOW}SKIPPED${NC}"
            ((TOTAL_TESTS--))
            ;;
    esac
done

echo ""
echo -e "Summary: ${GREEN}$PASSED_TESTS${NC} / ${TOTAL_TESTS} tests passed"

if [ $PASSED_TESTS -eq $TOTAL_TESTS ]; then
    echo -e "\n${GREEN}✓ All tests passed! Your DingTalk webhook bot is configured correctly.${NC}\n"
    exit 0
else
    FAILED=$((TOTAL_TESTS - PASSED_TESTS))
    echo -e "\n${YELLOW}⚠ $FAILED test(s) failed. Review the errors above.${NC}\n"
    exit 1
fi
