# Authentication

This document covers the authentication flow for BuffettGPT using Google OAuth and JWT tokens.

## Overview

BuffettGPT supports two authentication modes:

1. **Authenticated Users**: Google OAuth with JWT tokens (500 messages/month)
2. **Anonymous Users**: Device fingerprinting (5 messages/month)

## OAuth Flow

```
┌─────────┐     ┌─────────────┐     ┌─────────────┐
│ Client  │────▶│   Google    │────▶│  Callback   │
│         │     │   OAuth     │     │   Lambda    │
└─────────┘     └─────────────┘     └─────────────┘
     │                                     │
     │                                     ▼
     │                              ┌─────────────┐
     │◀─────────────────────────────│  JWT Token  │
     │                              └─────────────┘
```

### 1. Initiate OAuth

Redirect user to Google OAuth:

```javascript
const googleAuthUrl = `https://accounts.google.com/o/oauth2/v2/auth?
  client_id=${GOOGLE_CLIENT_ID}&
  redirect_uri=${REDIRECT_URI}&
  response_type=code&
  scope=openid email profile&
  access_type=offline`;

window.location.href = googleAuthUrl;
```

### 2. Handle Callback

The callback Lambda (`auth_callback.py`) handles the OAuth response:

1. Exchanges authorization code for tokens
2. Retrieves user profile from Google
3. Creates/updates user in DynamoDB
4. Issues JWT token

### 3. Store Token

```javascript
// Store JWT in localStorage
localStorage.setItem('buffett_token', response.token);
localStorage.setItem('buffett_user', JSON.stringify(response.user));
```

## JWT Token

### Token Structure

```json
{
  "sub": "user-uuid",
  "email": "user@example.com",
  "name": "John Doe",
  "iat": 1704067200,
  "exp": 1704153600
}
```

### Token Expiration

- **Access Token**: 24 hours
- **Refresh**: Re-authenticate via OAuth

### Using the Token

Include in `Authorization` header:

```javascript
fetch('/api/conversations', {
  headers: {
    'Authorization': `Bearer ${token}`
  }
});
```

Or as WebSocket query parameter:

```javascript
new WebSocket(`${WS_URL}?token=${token}`);
```

## JWT Verification

The `auth_verify.py` Lambda authorizer:

1. Extracts token from header/query
2. Verifies signature using secret
3. Checks expiration
4. Returns IAM policy for API Gateway

### Verification Response

```json
{
  "principalId": "user-uuid",
  "policyDocument": {
    "Version": "2012-10-17",
    "Statement": [{
      "Action": "execute-api:Invoke",
      "Effect": "Allow",
      "Resource": "arn:aws:execute-api:*:*:*"
    }]
  },
  "context": {
    "userId": "user-uuid",
    "email": "user@example.com"
  }
}
```

## Anonymous Users

For unauthenticated requests, device fingerprinting is used:

### Fingerprint Components

- Client IP address
- User-Agent header
- CloudFront viewer headers
- Accept-Language header

### Fingerprint Generation

```python
fingerprint_data = f"{ip}:{user_agent}:{cf_headers}"
device_fingerprint = hashlib.sha256(fingerprint_data.encode()).hexdigest()
```

### Rate Limiting

Anonymous users are tracked in `anonymous-sessions` table with 5 messages/month limit.

## Security Considerations

### Token Storage

!!! warning "Security"
    Never store tokens in:
    - URL parameters (except WebSocket)
    - Cookies without HttpOnly flag
    - Unencrypted storage

Recommended: Use `localStorage` with HTTPS only.

### CORS Configuration

API Gateway is configured with strict CORS:

```yaml
AllowOrigins:
  - https://your-domain.com
AllowMethods:
  - GET
  - POST
  - OPTIONS
AllowHeaders:
  - Authorization
  - Content-Type
```

### Secret Rotation

JWT secrets are stored in AWS Secrets Manager and should be rotated periodically:

```bash
aws secretsmanager rotate-secret \
  --secret-id buffett-dev-jwt-secret
```

## Troubleshooting

### Invalid Token

```json
{
  "error": "INVALID_TOKEN",
  "message": "Token signature verification failed"
}
```

**Solution**: Re-authenticate via OAuth.

### Expired Token

```json
{
  "error": "TOKEN_EXPIRED",
  "message": "Token has expired"
}
```

**Solution**: Redirect to OAuth flow.

### Missing Token

```json
{
  "error": "UNAUTHORIZED",
  "message": "No authorization token provided"
}
```

**Solution**: Include token in request.
