"""
Subscription management system for GrowVRD.

This module provides functionality for managing user subscriptions,
handling tier features, upgrades, downgrades, and quota management.
"""
import logging
import time
import uuid
import hashlib
import json
from typing import Dict, List, Any, Optional, Tuple, Set, Union
from datetime import datetime, timedelta
from enum import Enum, auto
from threading import RLock

from core.oauth_sheets_connector import (
    get_user_by_email,
    update_users_data,
    get_users_data
)

# Set up logging
logger = logging.getLogger('subscription_manager')

# In-memory cache for subscription data
_subscription_cache = {}
_subscription_cache_lock = RLock()
_subscription_cache_ttl = 300  # 5 minutes


class SubscriptionTier(str, Enum):
    """Enum for subscription tiers"""
    FREE = "free"
    SUBSCRIBER = "subscriber"
    PREMIUM = "premium"


class SubscriptionError(Exception):
    """Exception raised for subscription-related errors"""
    pass


class SubscriptionFeature:
    """Class representing a subscription feature"""

    def __init__(
            self,
            name: str,
            description: str,
            tiers: List[SubscriptionTier] = None,
            limits: Dict[SubscriptionTier, int] = None
    ):
        self.name = name
        self.description = description
        self.tiers = tiers or [SubscriptionTier.PREMIUM]
        self.limits = limits or {}


# Define subscription plans and features
class SubscriptionPlans:
    """Class containing subscription plan definitions"""

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
            'description': 'Enhanced access with custom plant kits and advanced analytics',
            'features': []
        },
        SubscriptionTier.PREMIUM: {
            'name': 'Premium',
            'price_monthly': 9.99,
            'price_yearly': 99.99,
            'description': 'Complete access with unlimited plants and priority support',
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
        SubscriptionFeature(
            'plant_care_information',
            'Access plant care guides',
            [SubscriptionTier.FREE, SubscriptionTier.SUBSCRIBER, SubscriptionTier.PREMIUM]
        ),

        # Subscriber features
        SubscriptionFeature(
            'custom_kits',
            'Create and save custom plant kits',
            [SubscriptionTier.SUBSCRIBER, SubscriptionTier.PREMIUM],
            {
                SubscriptionTier.SUBSCRIBER: 5,
                SubscriptionTier.PREMIUM: 20
            }
        ),
        SubscriptionFeature(
            'detailed_analytics',
            'Access detailed plant analytics',
            [SubscriptionTier.SUBSCRIBER, SubscriptionTier.PREMIUM]
        ),
        SubscriptionFeature(
            'service_fee_discount',
            'Reduced service fees (3% vs 10%)',
            [SubscriptionTier.SUBSCRIBER, SubscriptionTier.PREMIUM]
        ),
        SubscriptionFeature(
            'premium_content',
            'Access premium plant content',
            [SubscriptionTier.SUBSCRIBER, SubscriptionTier.PREMIUM]
        ),

        # Premium features
        SubscriptionFeature(
            'unlimited_plants',
            'Unlimited plant tracking',
            [SubscriptionTier.PREMIUM]
        ),
        SubscriptionFeature(
            'priority_support',
            'Priority customer support',
            [SubscriptionTier.PREMIUM]
        ),
        SubscriptionFeature(
            'scheduled_reminders',
            'Personalized care reminders',
            [SubscriptionTier.PREMIUM]
        ),
        SubscriptionFeature(
            'api_access',
            'API access for external integrations',
            [SubscriptionTier.PREMIUM],
            {
                SubscriptionTier.PREMIUM: 10000  # API calls per month
            }
        )
    ]

    # Update plan features
    for feature in FEATURES:
        for tier in feature.tiers:
            if tier in PLANS:
                PLANS[tier]['features'].append(feature.name)

    @classmethod
    def get_plan(cls, tier: SubscriptionTier) -> Dict[str, Any]:
        """Get plan details for a specific tier"""
        return cls.PLANS.get(tier, cls.PLANS[SubscriptionTier.FREE])

    @classmethod
    def get_feature(cls, feature_name: str) -> Optional[SubscriptionFeature]:
        """Get feature details by name"""
        for feature in cls.FEATURES:
            if feature.name == feature_name:
                return feature
        return None

    @classmethod
    def can_access_feature(cls, tier: SubscriptionTier, feature_name: str) -> bool:
        """Check if a tier can access a specific feature"""
        feature = cls.get_feature(feature_name)
        return feature is not None and tier in feature.tiers

    @classmethod
    def get_feature_limit(cls, tier: SubscriptionTier, feature_name: str) -> Optional[int]:
        """Get the limit for a feature in a specific tier"""
        feature = cls.get_feature(feature_name)
        if feature is None:
            return None
        return feature.limits.get(tier)


class SubscriptionQuotaManager:
    """Class for managing user quotas based on subscription tier"""

    # In-memory quota tracking (use Redis or a database in production)
    _user_quotas = {}
    _quota_lock = RLock()

    @classmethod
    def check_quota(cls, email: str, feature: str) -> Tuple[bool, str, Optional[int]]:
        """
        Check if a user has exceeded their quota for a feature.

        Args:
            email: User's email address
            feature: Feature name to check quota for

        Returns:
            Tuple of (has_quota, message, remaining)
        """
        try:
            user = get_user_by_email(email)
            if not user:
                return False, "User not found", None

            tier_str = user.get('subscription_status', 'free')
            try:
                tier = SubscriptionTier(tier_str)
            except ValueError:
                tier = SubscriptionTier.FREE

            # Check if feature has a limit
            limit = SubscriptionPlans.get_feature_limit(tier, feature)
            if limit is None:
                # No limit for this feature at this tier
                return True, "No quota limit for this feature", None

            # Check current usage
            with cls._quota_lock:
                quota_key = f"{email}:{feature}"

                if quota_key not in cls._user_quotas:
                    # Initialize quota tracking
                    now = datetime.now()
                    month_key = now.strftime("%Y-%m")

                    cls._user_quotas[quota_key] = {
                        'period': month_key,
                        'usage': 0,
                        'limit': limit
                    }

                # Check if period has reset
                quota = cls._user_quotas[quota_key]
                now = datetime.now()
                current_month = now.strftime("%Y-%m")

                if quota['period'] != current_month:
                    # Reset for new month
                    quota['period'] = current_month
                    quota['usage'] = 0

                # Check remaining quota
                remaining = quota['limit'] - quota['usage']

                if remaining <= 0:
                    return (
                        False,
                        f"Quota exceeded for {feature}. Upgrade to increase your limit.",
                        0
                    )

                return (
                    True,
                    f"Quota available: {remaining} of {quota['limit']} remaining",
                    remaining
                )

        except Exception as e:
            logger.error(f"Error checking quota: {str(e)}")
            # Default to allowing access on error
            return True, "Error checking quota", None

    @classmethod
    def increment_usage(cls, email: str, feature: str, amount: int = 1) -> int:
        """
        Increment usage counter for a feature.

        Args:
            email: User's email address
            feature: Feature name
            amount: Amount to increment by

        Returns:
            Remaining quota
        """
        with cls._quota_lock:
            quota_key = f"{email}:{feature}"

            # Initial check to ensure quota exists
            has_quota, _, _ = cls.check_quota(email, feature)

            if quota_key in cls._user_quotas:
                # Increment usage
                cls._user_quotas[quota_key]['usage'] += amount

                # Calculate remaining
                remaining = cls._user_quotas[quota_key]['limit'] - cls._user_quotas[quota_key]['usage']
                return max(0, remaining)

            return 0

    @classmethod
    def get_usage_report(cls, email: str) -> Dict[str, Any]:
        """
        Get usage report for a user across all features.

        Args:
            email: User's email address

        Returns:
            Dictionary with usage statistics
        """
        user = get_user_by_email(email)
        if not user:
            return {"error": "User not found"}

        tier_str = user.get('subscription_status', 'free')
        try:
            tier = SubscriptionTier(tier_str)
        except ValueError:
            tier = SubscriptionTier.FREE

        report = {
            'user_email': email,
            'subscription_tier': tier.value,
            'subscription_plan': SubscriptionPlans.get_plan(tier)['name'],
            'features': {}
        }

        # Get usage for all features
        for feature in SubscriptionPlans.FEATURES:
            if tier in feature.tiers:
                quota_key = f"{email}:{feature.name}"

                if quota_key in cls._user_quotas:
                    quota = cls._user_quotas[quota_key]
                    limit = quota['limit']
                    usage = quota['usage']
                    remaining = max(0, limit - usage)

                    report['features'][feature.name] = {
                        'limit': limit,
                        'usage': usage,
                        'remaining': remaining,
                        'period': quota['period']
                    }
                else:
                    # Feature not used yet
                    limit = SubscriptionPlans.get_feature_limit(tier, feature.name)

                    report['features'][feature.name] = {
                        'limit': limit,
                        'usage': 0,
                        'remaining': limit,
                        'period': datetime.now().strftime("%Y-%m")
                    }

        return report


class SubscriptionManager:
    """Main class for subscription management"""

    @staticmethod
    def get_user_tier(email: str) -> SubscriptionTier:
        """
        Get the subscription tier for a user.

        Args:
            email: User's email address

        Returns:
            Subscription tier enum
        """
        # Check cache first
        with _subscription_cache_lock:
            if email in _subscription_cache:
                cached_tier, timestamp = _subscription_cache[email]
                age = datetime.now() - timestamp

                if age.total_seconds() < _subscription_cache_ttl:
                    return cached_tier

        # Cache miss or expired - fetch from database
        try:
            user = get_user_by_email(email)
            if not user:
                return SubscriptionTier.FREE

            tier_str = user.get('subscription_status', 'free')
            try:
                tier = SubscriptionTier(tier_str)
            except ValueError:
                tier = SubscriptionTier.FREE

            # Update cache
            with _subscription_cache_lock:
                _subscription_cache[email] = (tier, datetime.now())

            return tier

        except Exception as e:
            logger.error(f"Error getting subscription tier: {str(e)}")
            return SubscriptionTier.FREE

    @staticmethod
    def can_access_feature(email: str, feature_name: str) -> bool:
        """
        Check if a user can access a specific feature.

        Args:
            email: User's email address
            feature_name: Name of the feature to check

        Returns:
            True if user can access the feature, False otherwise
        """
        tier = SubscriptionManager.get_user_tier(email)
        return SubscriptionPlans.can_access_feature(tier, feature_name)

    @staticmethod
    def check_feature_quota(email: str, feature_name: str) -> Tuple[bool, str, Optional[int]]:
        """
        Check if a user has quota for a specific feature.

        Args:
            email: User's email address
            feature_name: Name of the feature to check

        Returns:
            Tuple of (has_quota, message, remaining)
        """
        return SubscriptionQuotaManager.check_quota(email, feature_name)

    @staticmethod
    def track_feature_usage(email: str, feature_name: str, amount: int = 1) -> int:
        """
        Track usage of a feature.

        Args:
            email: User's email address
            feature_name: Name of the feature used
            amount: Amount to increment usage by

        Returns:
            Remaining quota
        """
        return SubscriptionQuotaManager.increment_usage(email, feature_name, amount)

    @staticmethod
    def get_tier_features(tier: SubscriptionTier) -> List[Dict[str, Any]]:
        """
        Get all features available for a tier.

        Args:
            tier: Subscription tier

        Returns:
            List of feature dictionaries
        """
        features = []

        for feature in SubscriptionPlans.FEATURES:
            if tier in feature.tiers:
                feature_data = {
                    'name': feature.name,
                    'description': feature.description,
                    'limit': feature.limits.get(tier)
                }
                features.append(feature_data)

        return features

    @staticmethod
    def get_user_features(email: str) -> List[Dict[str, Any]]:
        """
        Get all features available to a user.

        Args:
            email: User's email address

        Returns:
            List of feature dictionaries with usage information
        """
        tier = SubscriptionManager.get_user_tier(email)
        tier_features = SubscriptionManager.get_tier_features(tier)

        # Add usage information
        usage_report = SubscriptionQuotaManager.get_usage_report(email)

        for feature in tier_features:
            name = feature['name']
            if name in usage_report.get('features', {}):
                feature['usage'] = usage_report['features'][name].get('usage', 0)
                feature['remaining'] = usage_report['features'][name].get('remaining', feature['limit'])
                feature['period'] = usage_report['features'][name].get('period', 'current')

        return tier_features

    @staticmethod
    def upgrade_subscription(
            email: str,
            target_tier: SubscriptionTier,
            payment_info: Optional[Dict[str, Any]] = None
    ) -> bool:
        """
        Upgrade a user's subscription tier.

        Args:
            email: User's email address
            target_tier: Target subscription tier
            payment_info: Optional payment information for paid tiers

        Returns:
            True if upgrade successful, False otherwise

        Raises:
            SubscriptionError: If upgrade fails
        """
        try:
            user = get_user_by_email(email)
            if not user:
                raise SubscriptionError(f"User not found: {email}")

            current_tier_str = user.get('subscription_status', 'free')

            try:
                current_tier = SubscriptionTier(current_tier_str)
            except ValueError:
                current_tier = SubscriptionTier.FREE

            # Check if this is actually an upgrade
            if current_tier == target_tier:
                return True  # Already at target tier

            tier_order = [SubscriptionTier.FREE, SubscriptionTier.SUBSCRIBER, SubscriptionTier.PREMIUM]

            if tier_order.index(current_tier) > tier_order.index(target_tier):
                logger.warning(f"Attempted downgrade from {current_tier} to {target_tier} via upgrade method")
                return False

            # Handle payment for paid tiers
            if target_tier != SubscriptionTier.FREE and not payment_info:
                raise SubscriptionError("Payment information required for paid tiers")

            if target_tier != SubscriptionTier.FREE:
                # Process payment (placeholder)
                logger.info(f"Processing payment for {email} upgrade to {target_tier}")
                # In a real implementation, call payment processor here

            # Update user subscription
            users_data = get_users_data()
            updated = False

            for i, user_data in enumerate(users_data):
                if user_data.get('email') == email:
                    users_data[i]['subscription_status'] = target_tier.value
                    users_data[i]['subscription_updated_at'] = datetime.now().isoformat()

                    # Store subscription metadata
                    if 'subscription_metadata' not in users_data[i]:
                        users_data[i]['subscription_metadata'] = {}

                    users_data[i]['subscription_metadata']['previous_tier'] = current_tier.value
                    users_data[i]['subscription_metadata']['upgrade_date'] = datetime.now().isoformat()

                    updated = True
                    break

            if not updated:
                raise SubscriptionError(f"User data not updated: {email}")

            # Save to database
            update_users_data(users_data)

            # Update cache
            with _subscription_cache_lock:
                _subscription_cache[email] = (target_tier, datetime.now())

            logger.info(f"Successfully upgraded {email} from {current_tier} to {target_tier}")
            return True

        except Exception as e:
            error_msg = f"Error upgrading subscription: {str(e)}"
            logger.error(error_msg)
            raise SubscriptionError(error_msg)

    @staticmethod
    def downgrade_subscription(email: str, target_tier: SubscriptionTier) -> bool:
        """
        Downgrade a user's subscription tier.

        Args:
            email: User's email address
            target_tier: Target subscription tier

        Returns:
            True if downgrade successful, False otherwise

        Raises:
            SubscriptionError: If downgrade fails
        """
        try:
            user = get_user_by_email(email)
            if not user:
                raise SubscriptionError(f"User not found: {email}")

            current_tier_str = user.get('subscription_status', 'free')

            try:
                current_tier = SubscriptionTier(current_tier_str)
            except ValueError:
                current_tier = SubscriptionTier.FREE

            # Check if this is actually a downgrade
            if current_tier == target_tier:
                return True  # Already at target tier

            tier_order = [SubscriptionTier.FREE, SubscriptionTier.SUBSCRIBER, SubscriptionTier.PREMIUM]

            if tier_order.index(current_tier) < tier_order.index(target_tier):
                logger.warning(f"Attempted upgrade from {current_tier} to {target_tier} via downgrade method")
                return False

            # Handle cancellation of paid tiers
            if current_tier != SubscriptionTier.FREE:
                # Cancel subscription in payment processor (placeholder)
                logger.info(f"Cancelling paid subscription for {email}")
                # In a real implementation, call payment processor here

            # Update user subscription
            users_data = get_users_data()
            updated = False

            for i, user_data in enumerate(users_data):
                if user_data.get('email') == email:
                    users_data[i]['subscription_status'] = target_tier.value
                    users_data[i]['subscription_updated_at'] = datetime.now().isoformat()

                    # Store subscription metadata
                    if 'subscription_metadata' not in users_data[i]:
                        users_data[i]['subscription_metadata'] = {}

                    users_data[i]['subscription_metadata']['previous_tier'] = current_tier.value
                    users_data[i]['subscription_metadata']['downgrade_date'] = datetime.now().isoformat()

                    updated = True
                    break

            if not updated:
                raise SubscriptionError(f"User data not updated: {email}")

            # Save to database
            update_users_data(users_data)

            # Update cache
            with _subscription_cache_lock:
                _subscription_cache[email] = (target_tier, datetime.now())

            logger.info(f"Successfully downgraded {email} from {current_tier} to {target_tier}")
            return True

        except Exception as e:
            error_msg = f"Error downgrading subscription: {str(e)}"
            logger.error(error_msg)
            raise SubscriptionError(error_msg)

    @staticmethod
    def get_subscription_details(email: str) -> Dict[str, Any]:
        """
        Get detailed subscription information for a user.

        Args:
            email: User's email address

        Returns:
            Dictionary with subscription details
        """
        try:
            user = get_user_by_email(email)
            if not user:
                return {"error": "User not found"}

            tier_str = user.get('subscription_status', 'free')
            try:
                tier = SubscriptionTier(tier_str)
            except ValueError:
                tier = SubscriptionTier.FREE

            # Get plan details
            plan = SubscriptionPlans.get_plan(tier)

            # Get feature details with usage
            features = SubscriptionManager.get_user_features(email)

            # Get subscription metadata
            metadata = user.get('subscription_metadata', {})
            if not isinstance(metadata, dict):
                try:
                    if isinstance(metadata, str):
                        metadata = json.loads(metadata)
                    else:
                        metadata = {}
                except json.JSONDecodeError:
                    metadata = {}

            # Format subscription start date
            start_date = metadata.get('subscription_started', user.get('join_date'))

            # Calculate next billing date (placeholder)
            next_billing = None
            if tier != SubscriptionTier.FREE:
                last_billing = metadata.get('last_billing_date')
                if last_billing:
                    try:
                        last_date = datetime.fromisoformat(last_billing)
                        next_billing = (last_date + timedelta(days=30)).isoformat()
                    except (ValueError, TypeError):
                        pass

            return {
                'user_email': email,
                'subscription_tier': tier.value,
                'plan_name': plan['name'],
                'plan_description': plan['description'],
                'price_monthly': plan['price_monthly'],
                'price_yearly': plan['price_yearly'],
                'features': features,
                'subscription_start': start_date,
                'next_billing_date': next_billing,
                'is_active': True  # Placeholder - implement status check in production
            }

        except Exception as e:
            logger.error(f"Error getting subscription details: {str(e)}")
            return {"error": f"Error retrieving subscription details: {str(e)}"}

    @staticmethod
    def get_upgrade_options(email: str) -> Dict[str, Any]:
        """
        Get available upgrade options for a user.

        Args:
            email: User's email address

        Returns:
            Dictionary with upgrade options
        """
        tier = SubscriptionManager.get_user_tier(email)

        # Define tier order
        tier_order = [SubscriptionTier.FREE, SubscriptionTier.SUBSCRIBER, SubscriptionTier.PREMIUM]

        # Get current tier index
        current_index = tier_order.index(tier)

        # Get available upgrades
        available_upgrades = []
        for i in range(current_index + 1, len(tier_order)):
            upgrade_tier = tier_order[i]
            plan = SubscriptionPlans.get_plan(upgrade_tier)

            # Calculate feature differences
            feature_gains = []
            for feature in SubscriptionPlans.FEATURES:
                if upgrade_tier in feature.tiers and tier not in feature.tiers:
                    feature_gains.append({
                        'name': feature.name,
                        'description': feature.description,
                        'limit': feature.limits.get(upgrade_tier)
                    })

            available_upgrades.append({
                'tier': upgrade_tier.value,
                'plan_name': plan['name'],
                'plan_description': plan['description'],
                'price_monthly': plan['price_monthly'],
                'price_yearly': plan['price_yearly'],
                'new_features': feature_gains
            })

        return {
            'current_tier': tier.value,
            'current_plan': SubscriptionPlans.get_plan(tier)['name'],
            'available_upgrades': available_upgrades
        }


def require_subscription(required_tier: SubscriptionTier):
    """
    Decorator to require a specific subscription tier for an endpoint.

    Args:
        required_tier: Minimum required subscription tier

    Returns:
        Decorated function
    """
    import functools
    from flask import request, jsonify, g

    def decorator(f):
        @functools.wraps(f)
        def decorated_function(*args, **kwargs):
            # Get user email from request
            user_email = g.user_email if hasattr(g, 'user_email') else None

            # If no user is authenticated, return error
            if not user_email:
                # Import APIResponse here to avoid circular imports
                from api_response import APIResponse
                return jsonify(APIResponse.authentication_error(
                    message="Authentication required"
                )), 401

            # Get user's subscription tier
            tier = SubscriptionManager.get_user_tier(user_email)

            # Define tier order for comparison
            tier_order = [SubscriptionTier.FREE, SubscriptionTier.SUBSCRIBER, SubscriptionTier.PREMIUM]

            # Check if user's tier meets the requirement
            if tier_order.index(tier) < tier_order.index(required_tier):
                # Import APIResponse here to avoid circular imports
                from api_response import APIResponse
                upgrade_options = SubscriptionManager.get_upgrade_options(user_email)

                return jsonify(APIResponse.authorization_error(
                    message=f"{required_tier.value.title()} subscription required",
                    details={
                        "current_tier": tier.value,
                        "required_tier": required_tier.value,
                        "upgrade_options": upgrade_options['available_upgrades']
                    }
                )), 403

            return f(*args, **kwargs)

        return decorated_function

    return decorator


def track_feature_usage(feature_name: str, amount: int = 1):
    """
    Decorator to track feature usage for quota management.

    Args:
        feature_name: Name of the feature to track
        amount: Amount to increment usage by

    Returns:
        Decorated function
    """
    import functools
    from flask import g, jsonify

    def decorator(f):
        @functools.wraps(f)
        def decorated_function(*args, **kwargs):
            # Get user email from request
            user_email = g.user_email if hasattr(g, 'user_email') else None

            # If no user is authenticated, skip tracking
            if not user_email:
                return f(*args, **kwargs)

            # Check if user can access the feature
            if not SubscriptionManager.can_access_feature(user_email, feature_name):
                # Import APIResponse here to avoid circular imports
                from api_response import APIResponse
                return jsonify(APIResponse.authorization_error(
                    message=f"Your subscription does not include access to {feature_name}",
                    details={"feature": feature_name}
                )), 403

            # Check if user has quota remaining
            has_quota, message, remaining = SubscriptionManager.check_feature_quota(
                user_email, feature_name
            )

            if not has_quota:
                # Import APIResponse here to avoid circular imports
                from api_response import APIResponse
                return jsonify(APIResponse.quota_exceeded_error(
                    message=message
                )), 403

            # Track usage
            try:
                # Call the endpoint first
                response = f(*args, **kwargs)

                # If successful, increment usage
                SubscriptionManager.track_feature_usage(user_email, feature_name, amount)

                return response
            except Exception as e:
                # Don't increment usage on error
                logger.error(f"Error in track_feature_usage decorator: {str(e)}")
                raise

        return decorated_function

    return decorator

class KitManager:
    """Manager for custom kit creation and storage"""

    @staticmethod
    def save_custom_kit(
            user_email: str,
            kit_data: Dict[str, Any],
            tier: SubscriptionTier
    ) -> Dict[str, Any]:
        """
        Save a custom kit configuration for a user (subscribers only).

        Args:
            user_email: User's email address
            kit_data: Kit configuration data
            tier: User's subscription tier

        Returns:
            Response with status and message
        """
        # Check if user can access this feature
        if not SubscriptionPlans.can_access_feature(tier, 'custom_kits'):
            return {
                'success': False,
                'message': "Saving custom kits is a subscriber-only feature. Please upgrade your account."
            }

        try:
            # Generate a unique kit ID if not provided
            if 'kit_id' not in kit_data:
                kit_data['kit_id'] = f"custom_{uuid.uuid4().hex[:8]}"

            # Add metadata
            kit_data['created_at'] = datetime.now().isoformat()
            kit_data['last_modified'] = datetime.now().isoformat()
            kit_data['is_custom'] = True

            # Validate required fields
            required_fields = ['name', 'plant_ids']
            missing_fields = [field for field in required_fields if field not in kit_data]

            if missing_fields:
                return {
                    'success': False,
                    'message': f"Missing required fields: {', '.join(missing_fields)}"
                }

            # Save the kit
            result = update_user_kit(user_email, kit_data['kit_id'], kit_data)

            if result:
                return {
                    'success': True,
                    'message': "Custom kit saved successfully",
                    'kit_id': kit_data['kit_id']
                }
            else:
                return {
                    'success': False,
                    'message': "Failed to save custom kit. Please try again."
                }

        except Exception as e:
            logger.error(f"Error saving custom kit: {str(e)}")
            return {
                'success': False,
                'message': f"An error occurred: {str(e)}"
            }

    @staticmethod
    def get_user_custom_kits(user_email: str) -> List[Dict[str, Any]]:
        """
        Retrieve all custom kits for a user.

        Args:
            user_email: User's email address

        Returns:
            List of custom kit dictionaries
        """
        try:
            user = get_user_by_email(user_email)
            if not user:
                logger.warning(f"User not found: {user_email}")
                return []

            custom_configurations = user.get('custom_configurations', {})
            if not isinstance(custom_configurations, dict):
                try:
                    if isinstance(custom_configurations, str):
                        custom_configurations = json.loads(custom_configurations)
                    else:
                        custom_configurations = {}
                except json.JSONDecodeError:
                    custom_configurations = {}

            custom_kits = []
            for kit_id, kit_data in custom_configurations.items():
                if isinstance(kit_data, dict) and kit_data.get('is_custom', False):
                    kit_copy = kit_data.copy()
                    kit_copy['id'] = kit_id
                    custom_kits.append(kit_copy)

            return custom_kits

        except Exception as e:
            logger.error(f"Error retrieving custom kits: {str(e)}")
            return []