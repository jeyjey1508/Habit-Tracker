#!/bin/bash

echo "🚀 Habit Tracker Setup"
echo "====================="
echo ""

# Check Python version
python_version=$(python3 --version 2>&1 | awk '{print $2}')
echo "✓ Python version: $python_version"
echo ""

# Create virtual environment
echo "📦 Creating virtual environment..."
python3 -m venv venv

# Activate virtual environment
echo "⚡ Activating virtual environment..."
if [[ "$OSTYPE" == "msys" || "$OSTYPE" == "win32" ]]; then
    source venv/Scripts/activate
else
    source venv/bin/activate
fi

# Install dependencies
echo "📥 Installing dependencies..."
pip install -r requirements.txt

# Create .env file if it doesn't exist
if [ ! -f .env ]; then
    echo "🔧 Creating .env file..."
    cp .env.example .env
    # Generate random secret key
    SECRET_KEY=$(python3 -c "import secrets; print(secrets.token_hex(32))")
    sed -i.bak "s/change-this-to-a-random-secret-key/$SECRET_KEY/" .env
    rm .env.bak 2>/dev/null || true
    echo "✓ .env file created with secure random secret key"
else
    echo "✓ .env file already exists"
fi

echo ""
echo "✅ Setup complete!"
echo ""
echo "To start the application:"
echo "  1. Activate virtual environment:"
if [[ "$OSTYPE" == "msys" || "$OSTYPE" == "win32" ]]; then
    echo "     venv\\Scripts\\activate"
else
    echo "     source venv/bin/activate"
fi
echo "  2. Run the app:"
echo "     python app.py"
echo ""
echo "Then open: http://localhost:5000"
echo ""