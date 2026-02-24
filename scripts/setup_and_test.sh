#!/bin/bash
# Setup and test script for Odoo ERP Agent

set -e

echo "╔═══════════════════════════════════════════════════════════════╗"
echo "║     Odoo ERP Agent - Setup & Test Script                      ║"
echo "╚═══════════════════════════════════════════════════════════════╝"
echo ""

# Check Python version
echo "Checking Python version..."
python3 --version

# Install dependencies
echo ""
echo "Installing dependencies..."
pip3 install -e . --quiet

# Check for Ollama
echo ""
echo "Checking for Ollama (local LLM)..."
if command -v ollama &> /dev/null; then
    echo "✓ Ollama is installed"

    # Check if Ollama is running
    if curl -s http://localhost:11434/api/tags > /dev/null 2>&1; then
        echo "✓ Ollama is running"

        # Check for models
        MODELS=$(curl -s http://localhost:11434/api/tags | python3 -c "import sys, json; print([m['name'] for m in json.load(sys.stdin).get('models', [])])" 2>/dev/null || echo "[]")
        echo "  Available models: $MODELS"

        if [ "$MODELS" = "[]" ]; then
            echo ""
            echo "No models found. To pull a model:"
            echo "  ollama pull mistral:7b"
        fi
    else
        echo "✗ Ollama is not running"
        echo "  Start with: ollama serve"
    fi
else
    echo "✗ Ollama not installed"
    echo "  Install with: brew install ollama"
fi

# Check for Groq API key
echo ""
echo "Checking for Groq API key..."
if [ -n "$GROQ_API_KEY" ]; then
    echo "✓ GROQ_API_KEY is set"
else
    echo "✗ GROQ_API_KEY not set"
    echo "  Get free API key at: https://console.groq.com"
    echo "  Then: export GROQ_API_KEY=your-key-here"
fi

# Run tests
echo ""
echo "Running module tests..."
python3 -c "
from src.schemas.shared_context import create_new_project
from src.schemas.interview_domains import ALL_DOMAINS
from src.branching.analyzer import ResponseAnalyzer
from src.branching.engine import BranchingEngine
from src.agents import SmartInterviewAgent

print('✓ All modules imported successfully')

# Quick test
ctx = create_new_project('Test', 'Manufacturing')
print(f'✓ Created project: {ctx.project_id}')

print(f'✓ Loaded {len(ALL_DOMAINS)} interview domains')

analyzer = ResponseAnalyzer()
analysis = analyzer.analyze('We use QuickBooks', 'What accounting software?', 'finance_accounting')
print(f'✓ Response analyzer working: detected {analysis.detected_systems}')

print('')
print('All tests passed!')
"

echo ""
echo "╔═══════════════════════════════════════════════════════════════╗"
echo "║     Setup Complete!                                           ║"
echo "╠═══════════════════════════════════════════════════════════════╣"
echo "║                                                               ║"
echo "║  To start an interview:                                       ║"
echo "║    python3 -m src.cli -c \"Company\" -i \"Industry\"              ║"
echo "║                                                               ║"
echo "║  For LLM-powered interviews, either:                          ║"
echo "║    1. Start Ollama: ollama serve                              ║"
echo "║    2. Or set: export GROQ_API_KEY=your-key                    ║"
echo "║                                                               ║"
echo "╚═══════════════════════════════════════════════════════════════╝"
