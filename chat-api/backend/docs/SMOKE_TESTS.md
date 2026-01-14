# Smoke Tests - Post-Deployment Validation

## Executive Summary

Smoke tests are automated health checks that run immediately after code deployments to verify that critical system components are functioning correctly. This document describes the smoke testing infrastructure implemented for the Deep Value Insights platform.

**Key Benefit:** Catches broken deployments within 30 seconds, before users encounter errors.

---

## Business Value

| Benefit | Description |
|---------|-------------|
| **Reduced Downtime** | Broken deployments are caught immediately, not hours later when users report issues |
| **Faster Recovery** | Mean Time to Recovery (MTTR) reduced from hours to minutes |
| **Quality Gate** | Automated checkpoint prevents bad code from reaching production |
| **Cost Savings** | Prevents customer-facing incidents that require emergency response |
| **Confidence** | Development team can deploy more frequently with less risk |

---

## What Gets Tested

The smoke tests validate two core Lambda functions:

### Investment Research Lambda
Serves investment research reports with streaming responses.

| Test | What It Validates |
|------|-------------------|
| Health Check | Container starts, dependencies load, API responds |
| TOC Fetch | DynamoDB connectivity, data retrieval works |

### Prediction Ensemble Lambda
Runs ML model inference for stock analysis (v3.6.5 models).

| Test | What It Validates |
|------|-------------------|
| Health Check | Container starts, FastAPI loads, models accessible |
| Analyze (AAPL) | Full inference pipeline works, returns valid predictions |

---

## How It Works

```
┌─────────────────────────────────────────────────────────────────────────┐
│                        CI/CD PIPELINE FLOW                               │
├─────────────────────────────────────────────────────────────────────────┤
│                                                                          │
│   Push to dev    Build Lambda     Deploy to      Run Smoke    Summary   │
│   branch         packages         AWS            Tests        Report    │
│                                                                          │
│      [1]            [2]             [3]            [4]          [5]     │
│       │              │               │              │            │      │
│       ▼              ▼               ▼              ▼            ▼      │
│   ┌───────┐     ┌─────────┐    ┌─────────┐    ┌─────────┐   ┌───────┐  │
│   │ Code  │────▶│  Build  │───▶│ Deploy  │───▶│  SMOKE  │──▶│ Done  │  │
│   │ Push  │     │ Backend │    │ Infra   │    │  TESTS  │   │       │  │
│   └───────┘     └─────────┘    └─────────┘    └────┬────┘   └───────┘  │
│                                                    │                    │
│                                               PASS │ FAIL               │
│                                                    │   │                │
│                                                    ▼   ▼                │
│                                              Continue  BLOCK            │
│                                                        (alert)          │
│                                                                          │
└─────────────────────────────────────────────────────────────────────────┘
```

**Timeline:** Smoke tests add approximately 30 seconds to the deployment pipeline.

---

## Failure Response

When smoke tests fail:

1. **Immediate:** CI/CD pipeline is blocked - deployment does not complete
2. **Visibility:** GitHub Actions shows red "smoke-tests" job with error details
3. **Next Steps:** Development team investigates CloudWatch logs and fixes the issue

### Common Failure Causes

| Failure | Likely Cause | Resolution |
|---------|--------------|------------|
| Health check timeout | Lambda cold start too slow | Check container size, dependencies |
| Health returns unhealthy | Application error on startup | Check CloudWatch logs for errors |
| Analyze returns error | Model loading failed | Verify S3 model files exist |
| Connection refused | Lambda not deployed correctly | Re-run deployment |

---

## Metrics & Monitoring

### Where to View Results

| Location | What You'll See |
|----------|-----------------|
| **GitHub Actions** | Real-time test execution, pass/fail status |
| **CloudWatch Logs** | Detailed Lambda execution logs if tests fail |
| **Deployment Summary** | Final status report with API endpoints |

### GitHub Actions Path
```
Repository → Actions → "Deploy to Dev" → smoke-tests job
```

---

## Testing the Smoke Tests

To verify the smoke tests correctly block deployments:

1. Go to **GitHub Actions** → **Deploy to Dev**
2. Click **Run workflow**
3. Check **"Force smoke test failure"** checkbox
4. Click **Run workflow**
5. Verify the `smoke-tests` job fails and blocks `deployment-summary`

This confirms the quality gate is working as expected.

---

## Cost Impact

| Resource | Cost Impact |
|----------|-------------|
| GitHub Actions | ~30 seconds additional compute per deployment |
| AWS Lambda | 4 invocations per deployment (health checks) |
| **Total** | Negligible - less than $0.01 per deployment |

---

## Future Enhancements

| Enhancement | Description | Priority |
|-------------|-------------|----------|
| Auto-rollback | Automatically revert to previous version on failure | Medium |
| Slack alerts | Notify team channel on smoke test failure | Low |
| Performance baselines | Alert if response times exceed thresholds | Low |
| Canary deployment | Test with small traffic percentage before full rollout | Future |

---

## Technical Reference

- **Script Location:** `chat-api/backend/scripts/smoke_test.sh`
- **CI/CD Workflow:** `.github/workflows/deploy-dev.yml`
- **Timeout:** 30 seconds per request
- **Test Ticker:** AAPL (Apple Inc.) - baseline test case

---

## Contact

For questions about smoke tests or deployment issues, contact the platform engineering team.

---

*Document Version: 1.0*
*Last Updated: January 2026*
