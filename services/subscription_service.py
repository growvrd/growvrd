"""Subscription management service for GrowVRD.

This module provides subscription management functionality including:
- Subscription tier definitions
- Feature access control
- Quota management
- User subscription details
"""

from enum import Enum
from typing import Dict, Any, List, Optional, Tuple, Union
from datetime import datetime, timedelta
from threading import RLock
import logging
import re
from email_validator import validate_email, EmailNotValidError
from functools import wraps

# Set up logging
logger = logging.getLogger(__name__)

# Constants
MAX_EMAIL_LENGTH = 254
MAX_FEATURE_NAME_LENGTH = 100

class SubscriptionTier(str, Enum):
    """Enum for subscription tiers.
    
    Attributes:
        FREE: Basic free tier with limited features
        SUBSCRIBER: Paid tier with additional features
        PREMIUM: Top tier with all features and highest limits
    """
    FREE = "free"
    SUBSCRIBER = "subscriber"
    PREMIUM = "premium"

class SubscriptionFeature:
    """Class representing a subscription feature.
    
    Attributes:
        name: Unique identifier for the feature
        description: Human-readable description of the feature
        tiers: List of subscription tiers that have access to this feature
        limits: Dictionary mapping tiers to their respective usage limits
    """
    
    def __init__(
        self,
        name: str,
        description: str,
        tiers: Optional[List[SubscriptionTier]] = None,
        limits: Optional[Dict[SubscriptionTier, int]] = None
    ) -> None:
        """Initialize a subscription feature.
        
        Args:
            name: Unique identifier for the feature
            description: Human-readable description
            tiers: List of tiers with access to this feature
            limits: Dictionary of tier-specific limits
            
        Raises:
            ValueError: If name or description is invalid
        """
        if not name or not isinstance(name, str) or len(name) > MAX_FEATURE_NAME_LENGTH:
            raise ValueError(f"Feature name must be a non-empty string under {MAX_FEATURE_NAME_LENGTH} characters")
        if not description or not isinstance(description, str):
            raise ValueError("Description must be a non-empty string")
            
        self.name = name
        self.description = description
        self.tiers = tiers or [SubscriptionTier.PREMIUM]
        self.limits = limits or {}

def validate_email_address(email: str) -> str:
    """Validate and normalize an email address.
    
    Args:
        email: Email address to validate
        
    Returns:
        Normalized email address
        
    Raises:
        ValueError: If email is invalid
    """
    if not email or not isinstance(email, str) or len(email) > MAX_EMAIL_LENGTH:
        raise ValueError("Invalid email format")
        
    try:
        # Validate and normalize the email
        valid = validate_email(email)
        return valid.email
    except EmailNotValidError as e:
        raise ValueError(f"Invalid email: {str(e)}") from e


def handle_subscription_errors(func):
    """Decorator to handle common subscription service errors."""
    @wraps(func)
    def wrapper(*args, **kwargs):
        try:
            return func(*args, **kwargs)
        except ValueError as e:
            logger.warning(f"Validation error in {func.__name__}: {str(e)}")
            raise
        except Exception as e:
            logger.error(f"Unexpected error in {func.__name__}: {str(e)}", exc_info=True)
            raise
    return wrapper


class SubscriptionService:
    """Service for managing user subscriptions and features.
    
    This service handles:
    - Subscription tier management
    - Feature access control
    - Usage quotas and limits
    - Subscription details and status
    
    Thread-safe implementation for concurrent access.
    """
    
    # Define subscription plans and features
    PLANS = {
        SubscriptionTier.FREE: {
            'name': 'Free Plan',
            'price_monthly': 0,
            'price_yearly': 0,
            'description': 'Basic access to plant recommendations',
            'features': []
        },
        SubscriptionTier.SUBSCRIBER: {
            'name': 'Subscriber',
            'price_monthly': 4.99,
            'price_yearly': 49.99,
            'description': 'Enhanced access with custom plant kits',
            'features': []
        },
        SubscriptionTier.PREMIUM: {
            'name': 'Premium',
            'price_monthly': 9.99,
            'price_yearly': 99.99,
            'description': 'Complete access with unlimited plants',
            'features': []
        }
    }
    
    FEATURES = [
        # Basic features (all tiers)
        SubscriptionFeature(
            'plant_recommendations',
            'Get personalized plant recommendations',
            [SubscriptionTier.FREE, SubscriptionTier.SUBSCRIBER, SubscriptionTier.PREMIUM],
            {
                SubscriptionTier.FREE: 10,
                SubscriptionTier.SUBSCRIBER: 30,
                SubscriptionTier.PREMIUM: 100
            }
        ),
        # Add more features as needed
    ]
    
    def __init__(self):
        """Initialize the subscription service."""
        self._user_quotas: Dict[Tuple[str, str], int] = {}
        self._quota_lock = RLock()
        self._initialize_features()
        
    def _initialize_features(self) -> None:
        """Initialize the feature definitions and validate them."""
        # Validate all features during initialization
        for feature in self.FEATURES:
            if not feature.tiers:
                logger.warning(f"Feature {feature.name} has no tiers defined")
    
    @handle_subscription_errors
    def get_user_tier(self, email: str) -> SubscriptionTier:
        """Get the subscription tier for a user.
        
        Args:
            email: User's email address
            
        Returns:
            SubscriptionTier: The user's subscription tier
            
        Raises:
            ValueError: If email is invalid
        """
        # Validate email
        email = validate_email_address(email)
        
        # TODO: Implement actual user tier lookup from database
        # For now, return FREE tier for all users
        return SubscriptionTier.FREE
    
    @handle_subscription_errors
    def can_access_feature(self, email: str, feature_name: str) -> bool:
        """Check if a user can access a specific feature.
        
        Args:
            email: User's email address
            feature_name: Name of the feature to check
            
        Returns:
            bool: True if the user can access the feature, False otherwise
            
        Raises:
            ValueError: If email or feature_name is invalid
        """
        if not feature_name or not isinstance(feature_name, str):
            raise ValueError("Feature name must be a non-empty string")
            
        email = validate_email_address(email)
        tier = self.get_user_tier(email)
        
        for feature in self.FEATURES:
            if feature.name == feature_name:
                return tier in feature.tiers
                
        logger.warning(f"Unknown feature: {feature_name}")
        return False
    
    @handle_subscription_errors
    def check_quota(self, email: str, feature_name: str) -> Tuple[bool, str, int]:
        """Check if a user has quota for a feature.
        
        Args:
            email: User's email address
            feature_name: Name of the feature to check
            
        Returns:
            Tuple containing:
                - bool: True if user has quota remaining
                - str: Status message
                - int: Remaining quota (-1 for unlimited)
                
        Raises:
            ValueError: If email or feature_name is invalid
        """
        if not feature_name or not isinstance(feature_name, str):
            raise ValueError("Feature name must be a non-empty string")
            
        email = validate_email_address(email)
        
        if not self.can_access_feature(email, feature_name):
            return False, "Feature not available in your plan", 0
            
        tier = self.get_user_tier(email)
        feature = next((f for f in self.FEATURES if f.name == feature_name), None)
        
        if not feature:
            logger.warning(f"Unknown feature: {feature_name}")
            return False, "Unknown feature", 0
            
        if tier not in feature.limits:
            return True, "No quota limit", -1
            
        limit = feature.limits[tier]
        used = self._get_usage(email, feature_name)
        remaining = max(0, limit - used)
        
        return remaining > 0, f"{remaining} of {limit} remaining", remaining
    
    @handle_subscription_errors
    def _get_usage(self, email: str, feature_name: str) -> int:
        """Get current usage for a feature.
        
        Args:
            email: User's email address
            feature_name: Name of the feature
            
        Returns:
            int: Current usage count
            
        Raises:
            ValueError: If email or feature_name is invalid
        """
        if not feature_name or not isinstance(feature_name, str):
            raise ValueError("Feature name must be a non-empty string")
            
        email = validate_email_address(email)
        
        with self._quota_lock:
            return self._user_quotas.get((email, feature_name), 0)
    
    @handle_subscription_errors
    def increment_usage(self, email: str, feature_name: str, amount: int = 1) -> int:
        """Increment usage counter for a feature.
        
        Args:
            email: User's email address
            feature_name: Name of the feature
            amount: Amount to increment by (default: 1)
            
        Returns:
            int: New usage count
            
        Raises:
            ValueError: If email, feature_name, or amount is invalid
        """
        if not feature_name or not isinstance(feature_name, str):
            raise ValueError("Feature name must be a non-empty string")
        if not isinstance(amount, int) or amount < 1:
            raise ValueError("Amount must be a positive integer")
            
        email = validate_email_address(email)
        
        with self._quota_lock:
            key = (email, feature_name)
            current = self._user_quotas.get(key, 0)
            self._user_quotas[key] = current + amount
            return self._user_quotas[key]
    
    @handle_subscription_errors
    def get_subscription_details(self, email: str) -> Dict[str, Any]:
        """Get subscription details for a user.
        
        Args:
            email: User's email address
            
        Returns:
            Dict containing subscription details including:
                - tier: Current subscription tier
                - plan: Plan details
                - status: Subscription status
                - next_billing_date: Next billing date
                
        Raises:
            ValueError: If email is invalid
        """
        email = validate_email_address(email)
        tier = self.get_user_tier(email)
        
        if tier not in self.PLANS:
            logger.error(f"Invalid tier '{tier}' for user {email}")
            raise ValueError("Invalid subscription tier")
            
        plan = self.PLANS[tier].copy()
        
        # Add feature usage information
        plan['features'] = []
        for feature in self.FEATURES:
            if tier in feature.tiers:
                try:
                    has_quota, message, remaining = self.check_quota(email, feature.name)
                    plan['features'].append({
                        'name': feature.name,
                        'description': feature.description,
                        'has_quota': has_quota,
                        'message': message,
                        'remaining': remaining
                    })
                except Exception as e:
                    logger.error(f"Error checking quota for {feature.name}: {str(e)}")
                    continue
                
        return {
            'tier': tier.value,
            'plan': plan,
            'status': 'active',
            'next_billing_date': (datetime.utcnow() + timedelta(days=30)).strftime('%Y-%m-%d'),
            'last_updated': datetime.utcnow().isoformat()
        }
