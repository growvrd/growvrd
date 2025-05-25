#!/bin/bash
# Essential GrowVRD Sync Script
# Run this in PyCharm terminal after making changes

echo "🌱 GrowVRD Sync to GitHub & Replit"
echo "=================================="

# Check if we're in a git repository
if ! git rev-parse --git-dir > /dev/null 2>&1; then
    echo "❌ Not in a git repository. Run from your GrowVRD project folder."
    exit 1
fi

# Check for uncommitted changes
if ! git diff-index --quiet HEAD --; then
    echo "📝 You have uncommitted changes:"
    git status --short
    echo
    read -p "Enter commit message: " commit_msg
    if [ -n "$commit_msg" ]; then
        git add .
        git commit -m "$commit_msg"
        echo "✅ Changes committed: $commit_msg"
    else
        echo "❌ No commit message provided. Aborting."
        exit 1
    fi
fi

# Push to GitHub
echo "📤 Pushing to GitHub..."
git push origin main

if [ $? -eq 0 ]; then
    echo "✅ Successfully pushed to GitHub"
    echo ""
    echo "🚀 Next: Update Replit by running this in Replit Shell:"
    echo "   git pull origin main"
    echo ""
    echo "🔗 Your Replit URL: https://replit.com/@yourusername/growvrd"
else
    echo "❌ Failed to push to GitHub"
    exit 1
fi