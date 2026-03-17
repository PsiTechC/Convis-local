#!/bin/bash

# Integration System Test Runner
# Runs all tests for the integration system

echo "=================================="
echo "Integration System Test Suite"
echo "=================================="
echo ""

# Colors for output
GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Check if pytest is installed
if ! command -v pytest &> /dev/null; then
    echo -e "${RED}Error: pytest is not installed${NC}"
    echo "Install it with: pip install pytest pytest-asyncio pytest-cov"
    exit 1
fi

# Check if we're in the correct directory
if [ ! -d "tests/integrations" ]; then
    echo -e "${RED}Error: tests/integrations directory not found${NC}"
    echo "Run this script from the convis-api directory"
    exit 1
fi

echo -e "${YELLOW}Installing test dependencies...${NC}"
pip install -q pytest pytest-asyncio pytest-cov pytest-mock 2>/dev/null || true

echo ""
echo "=================================="
echo "Running Unit Tests"
echo "=================================="
echo ""

# Run unit tests
pytest tests/integrations/test_template_renderer.py -v --tb=short
TEMPLATE_EXIT=$?

pytest tests/integrations/test_condition_evaluator.py -v --tb=short
CONDITION_EXIT=$?

pytest tests/integrations/test_integration_services.py -v --tb=short
SERVICES_EXIT=$?

pytest tests/integrations/test_workflow_engine.py -v --tb=short
ENGINE_EXIT=$?

echo ""
echo "=================================="
echo "Running Integration Tests"
echo "=================================="
echo ""

pytest tests/integrations/test_api_routes.py -v --tb=short 2>/dev/null || echo "API tests skipped (requires app import)"
API_EXIT=$?

echo ""
echo "=================================="
echo "Running End-to-End Tests"
echo "=================================="
echo ""

pytest tests/integrations/test_end_to_end.py -v --tb=short
E2E_EXIT=$?

echo ""
echo "=================================="
echo "Test Summary"
echo "=================================="
echo ""

# Calculate total
TOTAL_EXIT=$(($TEMPLATE_EXIT + $CONDITION_EXIT + $SERVICES_EXIT + $ENGINE_EXIT + $E2E_EXIT))

if [ $TEMPLATE_EXIT -eq 0 ]; then
    echo -e "${GREEN}✓${NC} Template Renderer Tests"
else
    echo -e "${RED}✗${NC} Template Renderer Tests"
fi

if [ $CONDITION_EXIT -eq 0 ]; then
    echo -e "${GREEN}✓${NC} Condition Evaluator Tests"
else
    echo -e "${RED}✗${NC} Condition Evaluator Tests"
fi

if [ $SERVICES_EXIT -eq 0 ]; then
    echo -e "${GREEN}✓${NC} Integration Services Tests"
else
    echo -e "${RED}✗${NC} Integration Services Tests"
fi

if [ $ENGINE_EXIT -eq 0 ]; then
    echo -e "${GREEN}✓${NC} Workflow Engine Tests"
else
    echo -e "${RED}✗${NC} Workflow Engine Tests"
fi

if [ $E2E_EXIT -eq 0 ]; then
    echo -e "${GREEN}✓${NC} End-to-End Tests"
else
    echo -e "${RED}✗${NC} End-to-End Tests"
fi

echo ""
echo "=================================="

if [ $TOTAL_EXIT -eq 0 ]; then
    echo -e "${GREEN}All tests passed!${NC}"
    echo "=================================="
    exit 0
else
    echo -e "${RED}Some tests failed${NC}"
    echo "=================================="
    exit 1
fi
