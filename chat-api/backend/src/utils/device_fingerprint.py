"""
Device Fingerprinting Utility
Generates stable device identifiers for anonymous users to enable rate limiting
without authentication.
"""

import hashlib
import json
import logging
from typing import Dict, Any, Optional, Tuple
from datetime import datetime

logger = logging.getLogger(__name__)

class DeviceFingerprinter:
    """
    Generates device fingerprints for anonymous user tracking and rate limiting.
    
    Uses multiple signals to create a stable identifier that persists across
    sessions but is difficult to spoof or bypass.
    """
    
    # Weights for different fingerprint components (higher = more important)
    COMPONENT_WEIGHTS = {
        'ip_address': 0.3,
        'user_agent': 0.25,
        'accept_language': 0.15,
        'accept_encoding': 0.1,
        'cf_country': 0.1,
        'cf_ray': 0.05,
        'cf_protocol': 0.05
    }
    
    @staticmethod
    def extract_headers(event: Dict[str, Any]) -> Dict[str, str]:
        """
        Extract relevant headers from API Gateway event.
        
        Args:
            event: API Gateway event object
            
        Returns:
            Dictionary of normalized headers
        """
        headers = event.get('headers', {})
        
        # Normalize header names (API Gateway may provide different cases)
        normalized_headers = {}
        for key, value in headers.items():
            normalized_headers[key.lower()] = value
        
        return normalized_headers
    
    @staticmethod
    def get_client_ip(event: Dict[str, Any]) -> str:
        """
        Extract client IP address from event, considering proxies and CloudFront.
        
        Args:
            event: API Gateway event object
            
        Returns:
            Client IP address or 'unknown'
        """
        headers = DeviceFingerprinter.extract_headers(event)
        
        # Priority order for IP extraction
        # 1. CloudFront original IP
        if 'cloudfront-viewer-address' in headers:
            # Format: "198.51.100.178:46532"
            ip_port = headers['cloudfront-viewer-address']
            return ip_port.split(':')[0] if ':' in ip_port else ip_port
        
        # 2. X-Forwarded-For header (may contain multiple IPs)
        if 'x-forwarded-for' in headers:
            # Take the first IP in the chain (original client)
            ips = headers['x-forwarded-for'].split(',')
            return ips[0].strip()
        
        # 3. API Gateway request context
        request_context = event.get('requestContext', {})
        identity = request_context.get('identity', {})
        if 'sourceIp' in identity:
            return identity['sourceIp']
        
        # 4. Direct connection IP (rare in API Gateway)
        if 'x-real-ip' in headers:
            return headers['x-real-ip']
        
        return 'unknown'
    
    @staticmethod
    def generate_fingerprint(event: Dict[str, Any]) -> str:
        """
        Generate a device fingerprint from API Gateway event.
        
        Args:
            event: API Gateway event object
            
        Returns:
            Device fingerprint string (prefixed with 'anon_')
        """
        headers = DeviceFingerprinter.extract_headers(event)
        
        # Collect fingerprint components
        fingerprint_data = {
            'ip_address': DeviceFingerprinter.get_client_ip(event),
            'user_agent': headers.get('user-agent', ''),
            'accept_language': headers.get('accept-language', ''),
            'accept_encoding': headers.get('accept-encoding', ''),
            'cf_country': headers.get('cloudfront-viewer-country', ''),
            'cf_ray': headers.get('cf-ray', ''),
            'cf_protocol': headers.get('cloudfront-is-desktop-viewer', '') + 
                          headers.get('cloudfront-is-mobile-viewer', '') +
                          headers.get('cloudfront-is-tablet-viewer', '')
        }
        
        # Additional browser fingerprinting if available
        if 'sec-ch-ua' in headers:
            fingerprint_data['sec_ch_ua'] = headers['sec-ch-ua']
        if 'sec-ch-ua-platform' in headers:
            fingerprint_data['platform'] = headers['sec-ch-ua-platform']
        if 'sec-ch-ua-mobile' in headers:
            fingerprint_data['mobile'] = headers['sec-ch-ua-mobile']
        
        # Create stable hash
        fingerprint_string = json.dumps(fingerprint_data, sort_keys=True)
        device_hash = hashlib.sha256(fingerprint_string.encode()).hexdigest()
        
        # Use first 16 characters for readability
        device_id = f"anon_{device_hash[:16]}"
        
        logger.info(f"Generated device fingerprint", extra={
            'device_id': device_id,
            'ip_address': fingerprint_data['ip_address'],
            'user_agent_length': len(fingerprint_data['user_agent']),
            'has_cf_headers': bool(fingerprint_data['cf_country'])
        })
        
        return device_id
    
    @staticmethod
    def generate_fallback_fingerprint(event: Dict[str, Any]) -> str:
        """
        Generate a more lenient fingerprint for cases where primary signals are missing.
        
        Args:
            event: API Gateway event object
            
        Returns:
            Fallback device fingerprint
        """
        # Use only the most stable signals
        ip = DeviceFingerprinter.get_client_ip(event)
        headers = DeviceFingerprinter.extract_headers(event)
        user_agent = headers.get('user-agent', 'unknown')
        
        # Simple hash of IP + User Agent
        fallback_data = f"{ip}:{user_agent}"
        fallback_hash = hashlib.md5(fallback_data.encode()).hexdigest()
        
        return f"anon_fb_{fallback_hash[:12]}"
    
    @staticmethod
    def get_or_create_user_id(event: Dict[str, Any]) -> Tuple[str, str, Dict[str, Any]]:
        """
        Get user_id and user_type from event, supporting both authenticated and anonymous users.
        
        Args:
            event: API Gateway event object
            
        Returns:
            Tuple of (user_id, user_type, metadata)
            - user_id: Either Google sub claim or device fingerprint
            - user_type: 'authenticated' or 'anonymous'
            - metadata: Additional information about the user/device
        """
        metadata = {}
        
        # Check for authenticated user first
        request_context = event.get('requestContext', {})
        authorizer = request_context.get('authorizer', {})
        
        if authorizer and 'user_id' in authorizer:
            # Authenticated user via JWT
            user_id = authorizer['user_id']
            user_type = 'authenticated'
            
            # Get additional metadata from authorizer
            metadata = {
                'email': authorizer.get('email', ''),
                'session_id': authorizer.get('session_id', ''),
                'subscription_tier': authorizer.get('subscription_tier', 'free'),
                'auth_method': 'jwt'
            }
            
            logger.info(f"Authenticated user identified", extra={
                'user_id': user_id,
                'has_email': bool(metadata.get('email'))
            })
        else:
            # Anonymous user - generate device fingerprint
            device_id = DeviceFingerprinter.generate_fingerprint(event)
            user_id = device_id
            user_type = 'anonymous'
            
            # Collect anonymous user metadata
            headers = DeviceFingerprinter.extract_headers(event)
            metadata = {
                'device_fingerprint': device_id,
                'ip_address': DeviceFingerprinter.get_client_ip(event),
                'user_agent': headers.get('user-agent', ''),
                'country': headers.get('cloudfront-viewer-country', 'unknown'),
                'auth_method': 'device_fingerprint',
                'fingerprint_generated_at': datetime.utcnow().isoformat()
            }
            
            logger.info(f"Anonymous user identified", extra={
                'device_id': device_id,
                'country': metadata['country']
            })
        
        return user_id, user_type, metadata
    
    @staticmethod
    def validate_fingerprint(fingerprint: str) -> bool:
        """
        Validate that a fingerprint follows the expected format.
        
        Args:
            fingerprint: Device fingerprint string
            
        Returns:
            True if valid, False otherwise
        """
        if not fingerprint:
            return False
        
        # Check for anonymous prefix
        if not fingerprint.startswith('anon_'):
            return False
        
        # Check length (anon_ + 16 chars = 21, or anon_fb_ + 12 = 20)
        if len(fingerprint) not in [21, 20]:
            return False
        
        # Check that the hash portion is hexadecimal
        hash_part = fingerprint.replace('anon_', '').replace('fb_', '')
        try:
            int(hash_part, 16)
            return True
        except ValueError:
            return False
    
    @staticmethod
    def extract_device_info(event: Dict[str, Any]) -> Dict[str, Any]:
        """
        Extract detailed device information for analytics and debugging.
        
        Args:
            event: API Gateway event object
            
        Returns:
            Dictionary with device information
        """
        headers = DeviceFingerprinter.extract_headers(event)
        
        device_info = {
            'ip_address': DeviceFingerprinter.get_client_ip(event),
            'user_agent': headers.get('user-agent', ''),
            'accept_language': headers.get('accept-language', ''),
            'country': headers.get('cloudfront-viewer-country', ''),
            'is_desktop': headers.get('cloudfront-is-desktop-viewer', 'false') == 'true',
            'is_mobile': headers.get('cloudfront-is-mobile-viewer', 'false') == 'true',
            'is_tablet': headers.get('cloudfront-is-tablet-viewer', 'false') == 'true',
            'protocol': headers.get('cloudfront-viewer-protocol', ''),
            'tls_version': headers.get('cloudfront-viewer-tls', ''),
            'http_version': headers.get('cloudfront-viewer-http-version', ''),
            'timestamp': datetime.utcnow().isoformat()
        }
        
        # Parse user agent for browser/OS info if possible
        user_agent = device_info['user_agent']
        if user_agent:
            # Basic parsing (you might want to use a library like user-agents for better parsing)
            if 'Chrome' in user_agent:
                device_info['browser'] = 'Chrome'
            elif 'Safari' in user_agent and 'Chrome' not in user_agent:
                device_info['browser'] = 'Safari'
            elif 'Firefox' in user_agent:
                device_info['browser'] = 'Firefox'
            else:
                device_info['browser'] = 'Other'
            
            if 'Windows' in user_agent:
                device_info['os'] = 'Windows'
            elif 'Mac' in user_agent:
                device_info['os'] = 'macOS'
            elif 'Linux' in user_agent:
                device_info['os'] = 'Linux'
            elif 'Android' in user_agent:
                device_info['os'] = 'Android'
            elif 'iOS' in user_agent or 'iPhone' in user_agent or 'iPad' in user_agent:
                device_info['os'] = 'iOS'
            else:
                device_info['os'] = 'Other'
        
        return device_info


# Convenience functions for direct import
generate_fingerprint = DeviceFingerprinter.generate_fingerprint
get_or_create_user_id = DeviceFingerprinter.get_or_create_user_id
validate_fingerprint = DeviceFingerprinter.validate_fingerprint
extract_device_info = DeviceFingerprinter.extract_device_info