#!/bin/bash
# setup_promptfoo.sh
# Quick setup script for Promptfoo integration

set -e

echo "🚀 Setting up Promptfoo Integration for RAG API"
echo "================================================"

# Check if .env exists
if [ ! -f .env ]; then
    echo "📝 Creating .env file from .env.example..."
    cp .env.example .env
    echo "⚠️  Please edit .env and add your API keys!"
    echo ""
else
    echo "✓ .env file already exists"
fi

# Install dependencies
echo ""
echo "📦 Installing Python dependencies..."
pip install -r requirements.txt

# Create uploads directory
echo ""
echo "📁 Creating uploads directory..."
mkdir -p uploads

# Check if sample document exists
if [ ! -f sample_data/alice_in_wonderland.txt ]; then
    echo "⚠️  Sample document not found at sample_data/alice_in_wonderland.txt"
else
    echo "✓ Sample document ready"
fi

# Check if PostgreSQL is running
echo ""
echo "🗄️  Checking database connection..."
if command -v psql &> /dev/null; then
    PGPASSWORD="${POSTGRES_PASSWORD:-mypassword}" psql -h "${DB_HOST:-localhost}" -p "${DB_PORT:-5432}" -U "${POSTGRES_USER:-myuser}" -d "${POSTGRES_DB:-mydatabase}" -c "SELECT 1;" &> /dev/null && echo "✓ Database connection successful" || echo "⚠️  Could not connect to database. Make sure PostgreSQL is running."
else
    echo "⚠️  psql not found. Skipping database check."
fi

# Install promptfoo CLI (optional)
echo ""
echo "🛠️  Installing Promptfoo CLI..."
if command -v npm &> /dev/null; then
    npm install -g promptfoo
    echo "✓ Promptfoo CLI installed"
else
    echo "⚠️  npm not found. Skipping Promptfoo CLI installation."
    echo "   You can install it later with: npm install -g promptfoo"
fi

echo ""
echo "✅ Setup complete!"
echo ""
echo "📚 Next steps:"
echo "   1. Edit .env and add your API keys"
echo "   2. Start the database: docker-compose up -d db"
echo "   3. Start the API: python main.py"
echo "   4. Upload sample document:"
echo "      curl -X POST http://localhost:8000/embed \\"
echo "        -F 'file_id=alice_in_wonderland.txt' \\"
echo "        -F 'file=@sample_data/alice_in_wonderland.txt'"
echo "   5. Test chat endpoint:"
echo "      curl -X POST http://localhost:8000/chat \\"
echo "        -H 'Content-Type: application/json' \\"
echo "        -d '{\"query\": \"Who is Alice?\", \"file_id\": \"alice_in_wonderland.txt\"}'"
echo "   6. Run red-team tests: promptfoo eval"
echo ""
echo "📖 Read PROMPTFOO_INTEGRATION.md for complete documentation"
echo ""
