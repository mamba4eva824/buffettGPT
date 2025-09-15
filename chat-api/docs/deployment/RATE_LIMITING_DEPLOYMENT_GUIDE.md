# Anonymous User Rate Limiting - Deployment Guide

## 🎯 **Overview**

This implementation adds anonymous user rate limiting to prevent abuse while allowing legitimate users to try your service. The system limits anonymous users to **5 requests per device per month** using advanced device fingerprinting.

## 📋 **What Was Created**

### 1. **DynamoDB Tables**
- `buffett-chat-api-dev-rate-limits` - Monthly usage aggregates
- `buffett-chat-api-dev-usage-tracking` - Individual request tracking

### 2. **Rate Limiting Middleware**
- `lambda-functions/rate_limiter.py` - Python module with device fingerprinting
- Decorator pattern for easy integration
- Automatic cleanup via TTL (3 months)

### 3. **Updated Lambda Functions**
- `chat_http_handler.py` - Now includes rate limiting decorator
- Environment variables for configuration
- Graceful degradation if tables unavailable

### 4. **Terraform Configuration**
- New variables in `variables.tf`
- Rate limiting configuration in `terraform.tfvars`
- IAM permissions for DynamoDB access

### 5. **Testing Tools**
- `test_rate_limiting.py` - Comprehensive test script

## 🚀 **Deployment Steps**

### Step 1: Deploy Infrastructure
```bash
cd /Users/christopherweinreich/Documents/Projects/buffett_chat_api/chat-api

# Initialize and plan
terraform init
terraform plan

# Deploy (review the plan first!)
terraform apply
```

### Step 2: Verify Deployment
```bash
# Check if new tables were created
aws dynamodb list-tables --region us-east-1 | grep rate

# Expected output:
# buffett-chat-api-dev-rate-limits
# buffett-chat-api-dev-usage-tracking
```

### Step 3: Test Rate Limiting
```bash
# Get your API endpoint from Terraform output or AWS Console
API_ENDPOINT="https://YOUR-API-ID.execute-api.us-east-1.amazonaws.com/dev"

# Run the test script
python test_rate_limiting.py $API_ENDPOINT
```

## 📊 **Configuration**

Current settings in `terraform.tfvars`:
```hcl
anonymous_monthly_limit = 5           # 5 requests per month for anonymous users
authenticated_monthly_limit = 500     # Future authenticated users limit
enable_device_fingerprinting = true   # Advanced device identification
enable_rate_limiting = true          # Enable the rate limiting system
rate_limit_grace_period_hours = 1    # 1-hour grace period for new devices
```

## 🔧 **How It Works**

### Device Fingerprinting
The system creates a unique identifier using:
1. **Client IP address** (primary)
2. **User-Agent string** (browser/app signature)
3. **CloudFront headers** (country, device type)
4. **Accept-Language** (locale preference)

### Rate Limiting Logic
1. **Request arrives** → Extract device fingerprint
2. **Check usage** → Query monthly usage count
3. **Within limit?** → Allow request + record usage
4. **Over limit?** → Return 429 with rate limit headers

### Response Headers
All responses include:
```
X-RateLimit-Limit: 5
X-RateLimit-Remaining: 3  
X-RateLimit-Reset: 2024-02-01
```

## 💰 **Cost Impact**

**Additional Monthly Costs** (for 1000 anonymous users):
- DynamoDB: ~$2-3/month (pay-per-request)
- Lambda execution: ~$0.50/month 
- CloudWatch logs: ~$0.25/month
- **Total: ~$3-4/month**

## 🔍 **Monitoring**

### CloudWatch Metrics
- Lambda function duration/errors
- DynamoDB read/write capacity
- Rate limiting log events

### Key Log Messages
```
# Successful rate limit check
INFO: Grace period active for anon:a1b2c3d4...

# Rate limit exceeded  
WARNING: Rate limit exceeded for anon:a1b2c3d4...: 6/5

# Error handling
ERROR: Rate limiting error: Table not found
```

## 🛡️ **Security Features**

### 1. **Device Fingerprinting**
- Combines multiple headers for unique identification
- Resistant to simple IP rotation
- Degrades gracefully to IP-only if needed

### 2. **Privacy Protection**
- Fingerprints are hashed (SHA-256, 16 chars)
- No personally identifiable information stored
- Automatic cleanup via TTL

### 3. **Abuse Prevention**
- Monthly reset prevents gaming the system
- Grace period for legitimate new users
- Fail-open design maintains availability

## 🧪 **Testing Scenarios**

### Test 1: Normal Usage
```bash
# Should succeed for first 5 requests
curl -X POST $API_ENDPOINT/chat \
  -H "Content-Type: application/json" \
  -d '{"message": "Test message 1"}'
```

### Test 2: Rate Limit Exceeded
```bash
# 6th request should return 429
# Response: {"error": "Rate limit exceeded", "limit": 5, "reset_date": "2024-02-01"}
```

### Test 3: Different Device
```bash
# Different User-Agent should get separate limit
curl -X POST $API_ENDPOINT/chat \
  -H "Content-Type: application/json" \
  -H "User-Agent: DifferentApp/1.0" \
  -d '{"message": "Test from different device"}'
```

## 🔧 **Configuration Options**

### Adjusting Limits
Edit `terraform.tfvars`:
```hcl
# Increase anonymous limit to 10 per month
anonymous_monthly_limit = 10

# Disable rate limiting temporarily
enable_rate_limiting = false

# Disable advanced fingerprinting (IP-only)
enable_device_fingerprinting = false
```

Then redeploy:
```bash
terraform apply
```

### Environment-Specific Settings
```hcl
# For staging environment
anonymous_monthly_limit = 20

# For production environment  
anonymous_monthly_limit = 5
enable_device_fingerprinting = true
rate_limit_grace_period_hours = 0  # No grace period in prod
```

## 🚨 **Troubleshooting**

### Issue: Rate limiting not working
```bash
# Check Lambda logs
aws logs tail /aws/lambda/buffett-chat-api-dev-chat-http-handler --follow

# Check DynamoDB tables exist
aws dynamodb describe-table --table-name buffett-chat-api-dev-rate-limits
```

### Issue: Requests still going through after limit
- Check `ENABLE_RATE_LIMITING` environment variable
- Verify IAM permissions for DynamoDB access
- Check for Lambda errors in CloudWatch

### Issue: All requests blocked
- Check if grace period is configured
- Verify device fingerprinting is working
- Review recent error logs

## 🔄 **Next Steps**

Ready for **Phase 2: Google OAuth Authentication**:
1. User management tables
2. JWT token validation  
3. Authenticated user rate limiting (500/month)
4. Chat history for logged-in users

## 📊 **Success Metrics**

You'll know it's working when:
- ✅ First 5 anonymous requests succeed (200 status)
- ✅ 6th request returns 429 with proper error message
- ✅ Different devices get separate rate limits
- ✅ Rate limit headers present in all responses
- ✅ Monthly usage resets on 1st of each month

---

**Rate limiting successfully implemented! 🎉**

Your API is now protected against abuse while maintaining a good user experience for legitimate users.

