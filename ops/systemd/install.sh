#!/bin/bash
# Install Leviathan systemd service for current user

set -e

echo "Installing Leviathan systemd service..."

# Create directories
mkdir -p ~/.config/systemd/user
mkdir -p ~/.leviathan/logs

# Copy service file
cp ops/leviathan/leviathan.service ~/.config/systemd/user/

# Check for env file
if [ ! -f ~/.leviathan/env ]; then
    echo "⚠️  Environment file not found. Creating template..."
    cp ops/leviathan/env.example ~/.leviathan/env
    echo ""
    echo "❌ IMPORTANT: Edit ~/.leviathan/env and add your credentials:"
    echo "   - LEVIATHAN_CLAUDE_API_KEY"
    echo "   - GITHUB_TOKEN"
    echo "   - LEVIATHAN_CLAUDE_MODEL"
    echo ""
    echo "Then run: systemctl --user daemon-reload"
    echo "          systemctl --user start leviathan"
    exit 1
fi

# Reload systemd
systemctl --user daemon-reload

echo "✅ Leviathan service installed to ~/.config/systemd/user/leviathan.service"
echo ""
echo "Next steps:"
echo "  1. Start service:  systemctl --user start leviathan"
echo "  2. Enable on boot: systemctl --user enable leviathan"
echo "  3. Check status:   systemctl --user status leviathan"
echo "  4. View logs:      journalctl --user -u leviathan -f"
