#!/bin/bash

# Test script for generic webhook trigger
# Usage: ./test_webhook_trigger.sh <workflow_id> [webhook_token]

WORKFLOW_ID=$1
WEBHOOK_TOKEN=$2
API_URL="http://localhost:8000"

if [ -z "$WORKFLOW_ID" ]; then
    echo "Usage: ./test_webhook_trigger.sh <workflow_id> [webhook_token]"
    echo ""
    echo "Example:"
    echo "  ./test_webhook_trigger.sh 65abc123def456 my-secret-token"
    exit 1
fi

echo "======================================"
echo "Testing Generic Webhook Trigger"
echo "======================================"
echo "Workflow ID: $WORKFLOW_ID"
if [ -n "$WEBHOOK_TOKEN" ]; then
    echo "Webhook Token: $WEBHOOK_TOKEN"
fi
echo ""

# Prepare the request
REQUEST_DATA='{
  "customer_name": "John Doe",
  "customer_email": "john@example.com",
  "customer_phone": "+1234567890",
  "sentiment": "positive",
  "email_mentioned": true,
  "custom_field_1": "test value",
  "custom_field_2": 12345
}'

echo "Sending webhook request..."
echo "Request Data:"
echo "$REQUEST_DATA" | jq .
echo ""

# Make the request
if [ -n "$WEBHOOK_TOKEN" ]; then
    RESPONSE=$(curl -s -X POST \
        "$API_URL/api/workflows/webhook/$WORKFLOW_ID/trigger?webhook_token=$WEBHOOK_TOKEN" \
        -H "Content-Type: application/json" \
        -d "$REQUEST_DATA")
else
    RESPONSE=$(curl -s -X POST \
        "$API_URL/api/workflows/webhook/$WORKFLOW_ID/trigger" \
        -H "Content-Type: application/json" \
        -d "$REQUEST_DATA")
fi

echo "Response:"
echo "$RESPONSE" | jq .
echo ""

# Check if successful
if echo "$RESPONSE" | jq -e '.success' > /dev/null 2>&1; then
    echo "✅ Workflow triggered successfully!"
    EXECUTION_ID=$(echo "$RESPONSE" | jq -r '.execution_id')
    echo "Execution ID: $EXECUTION_ID"
else
    echo "❌ Failed to trigger workflow"
    echo "Error: $(echo "$RESPONSE" | jq -r '.detail // "Unknown error"')"
fi

echo ""
echo "======================================"
echo "Test completed"
echo "======================================"
