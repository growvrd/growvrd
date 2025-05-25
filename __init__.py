"""
GrowVRD - AI-Powered Plant Recommendation System
Root Package Initialization

This is the main package for GrowVRD, an intelligent plant care and recommendation
assistant that helps users select, maintain, and succeed with indoor plants.

Version: 1.0.0 (MVP with GitHub + Replit Integration)
Author: GrowVRD Team
"""

__version__ = "1.0.0"
__title__ = "GrowVRD"
__description__ = "AI-Powered Plant Recommendation System with Local Business Integration"
__author__ = "GrowVRD Team"
__license__ = "Proprietary"

# Package metadata
__all__ = [
    "app",
    "core",
    "api",
    "__version__",
    "__title__",
    "__description__"
]


# Import version info for easy access
def get_version_info():
    """Return version and build information"""
    return {
        "version": __version__,
        "title": __title__,
        "description": __description__,
        "build_date": "2025-01-23",
        "environment": "MVP",
        "status": "GitHub + Replit Deployed"
    }


# Health check function for the package
def health_check():
    """Perform basic health check of the package"""
    health_status = {
        "package": "healthy",
        "version": __version__,
        "core_modules": [],
        "api_modules": [],
        "issues": []
    }

    # Check core modules
    try:
        import core
        health_status["core_modules"].append("core")
    except ImportError as e:
        health_status["issues"].append(f"Core module issue: {e}")

    # Check API modules
    try:
        import api
        health_status["api_modules"].append("api")
    except ImportError as e:
        health_status["issues"].append(f"API module issue: {e}")

    # Check Flask app
    try:
        import app
        health_status["flask_app"] = "available"
    except ImportError as e:
        health_status["issues"].append(f"Flask app issue: {e}")
        health_status["flask_app"] = "unavailable"

    return health_status


# Development utilities
def get_debug_info():
    """Get comprehensive debug information for troubleshooting"""
    import os
    import sys

    return {
        "python_version": sys.version,
        "python_path": sys.path,
        "working_directory": os.getcwd(),
        "environment_variables": {
            "ENVIRONMENT": os.getenv("ENVIRONMENT", "not_set"),
            "USE_MOCK_DATA": os.getenv("USE_MOCK_DATA", "not_set"),
            "OPENAI_API_KEY": "***" if os.getenv("OPENAI_API_KEY") else "not_set",
            "PERENUAL_API_KEY": "***" if os.getenv("PERENUAL_API_KEY") else "not_set",
        },
        "package_health": health_check(),
        "version_info": get_version_info()
    }


# Quick setup validation
def validate_setup():
    """Validate that the GrowVRD setup is ready for deployment"""
    issues = []

    # Check required files
    required_files = [
        "app.py",
        "requirements.txt",
        ".env",
        ".gitignore",
        "static/chat.html",
        "core/__init__.py",
        "api/__init__.py"
    ]

    import os
    for file in required_files:
        if not os.path.exists(file):
            issues.append(f"Missing required file: {file}")

    # Check environment variables
    required_env_vars = ["OPENAI_API_KEY", "ENVIRONMENT"]
    for var in required_env_vars:
        if not os.getenv(var):
            issues.append(f"Missing environment variable: {var}")

    return {
        "ready_for_deployment": len(issues) == 0,
        "issues": issues,
        "status": "✅ Ready!" if len(issues) == 0 else f"❌ {len(issues)} issues found"
    }


# Print startup info when package is imported
if __name__ != "__main__":
    print(f"🌱 {__title__} v{__version__} - {__description__}")

    # Quick validation on import (only in development)
    import os

    if os.getenv("ENVIRONMENT") == "development":
        validation = validate_setup()
        if not validation["ready_for_deployment"]:
            print(f"⚠️  Setup validation: {validation['status']}")
            for issue in validation["issues"][:3]:  # Show first 3 issues
                print(f"   - {issue}")