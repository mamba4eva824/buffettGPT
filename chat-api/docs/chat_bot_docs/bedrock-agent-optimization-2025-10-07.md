# Bedrock Agent Optimization - October 7, 2025

## Overview

This document details the comprehensive optimization performed on the BuffettGPT Bedrock Agent in the dev environment. The changes focus on improving model capabilities, reducing restrictiveness, and enabling more flexible financial advice while maintaining safety and accuracy.

## Change Summary

| Component | Previous Value | New Value | Impact |
|-----------|---------------|-----------|--------|
| **Foundation Model** | Claude 3 Haiku (`anthropic.claude-3-haiku-20240307-v1:0`) | Claude 3.5 Haiku (`anthropic.claude-3-5-haiku-20241022-v1:0`) | Better reasoning, improved capabilities |
| **Temperature** | 0.0 (deterministic) | 0.3 (balanced) | More natural, varied responses |
| **Prompt Override** | Disabled | Enabled | Allows custom temperature and instructions |
| **Content Filters** | HIGH/MEDIUM | MEDIUM/LOW | Less restrictive filtering |
| **Contextual Grounding** | 0.75/0.8 | 0.65/0.7 | More flexible responses |

## Detailed Changes

### 1. Foundation Model Upgrade

**Change:**
- Upgraded from Claude 3 Haiku to Claude 3.5 Haiku
- Model ID: `anthropic.claude-3-5-haiku-20241022-v1:0`

**Benefits:**
- Enhanced reasoning capabilities
- Better understanding of complex financial concepts
- Improved context handling
- More natural language generation

**Configuration File:**
- `/chat-api/terraform/environments/dev/variables.tf` (line 100-104)

```hcl
variable "bedrock_foundation_model" {
  description = "Foundation model for Bedrock agent"
  type        = string
  default     = "anthropic.claude-3-5-haiku-20241022-v1:0"
}
```

### 2. Temperature Adjustment

**Change:**
- Orchestration Temperature: `0.0` → `0.3`
- Knowledge Base Temperature: Remains `0.0` (for factual accuracy)

**Benefits:**
- More conversational and natural responses
- Slight variation in phrasing while maintaining accuracy
- Less robotic feel
- Better user engagement

**Why 0.3?**
- Conservative increase from deterministic (0.0)
- Maintains high accuracy for financial advice
- Adds enough variation to feel natural
- Lower risk of hallucinations compared to higher values (0.7-1.0)

**Configuration:**
- Enabled via `enable_prompt_override = true` in `/chat-api/terraform/environments/dev/main.tf` (line 266)
- Temperature set in `/chat-api/terraform/modules/bedrock/variables.tf` (line 276-280)

### 3. Guardrails Optimization

#### Content Filters

**Changes:**

| Filter Type | Input Strength | Output Strength | Change |
|-------------|---------------|-----------------|--------|
| HATE | HIGH → MEDIUM | HIGH → MEDIUM | More permissive |
| INSULTS | MEDIUM → LOW | MEDIUM → LOW | Less restrictive |
| SEXUAL | HIGH → MEDIUM | HIGH → MEDIUM | More permissive |
| VIOLENCE | HIGH → MEDIUM | HIGH → MEDIUM | More permissive |
| MISCONDUCT | MEDIUM → LOW | MEDIUM → LOW | Less restrictive |
| PROMPT_ATTACK | HIGH → MEDIUM | NONE (unchanged) | More permissive input |

**Rationale:**
- Financial discussions rarely involve hate, sexual, or violence content
- Lower filters reduce false positives
- Still maintains safety for inappropriate content
- Allows more natural financial discussions

**Configuration:**
- `/chat-api/terraform/modules/bedrock/variables.tf` (lines 432-457)

#### Contextual Grounding Thresholds

**Changes:**

| Threshold Type | Previous | New | Change |
|----------------|----------|-----|--------|
| GROUNDING | 0.75 | 0.65 | -13% (more flexible) |
| RELEVANCE | 0.8 | 0.7 | -12.5% (more permissive) |

**Benefits:**
- Agent can apply Buffett's principles more broadly
- Better at extrapolating from general principles to specific scenarios
- Can synthesize information from multiple letters
- Still grounded in source material but less rigid

**Configuration:**
- `/chat-api/terraform/modules/bedrock/variables.tf` (lines 538-547)

### 4. Agent Instructions Enhancement

**Previous Instruction:**
Simple, basic instruction focused on answering questions from shareholder letters.

**New Instruction:**
Comprehensive, structured guidelines that:
- Define the agent as a financial advisor using Buffett's philosophies
- Allow principle-based extrapolation to current/hypothetical situations
- Provide structured response framework (Principle → Example → Application)
- Maintain Buffett's plainspoken style and folksy humor
- Enable clarifying questions for vague queries
- Set honest boundaries without guaranteeing specific stock returns

**Key Additions:**
```
PRINCIPLES: You may apply Buffett's timeless investment principles to current or hypothetical situations, as long as you:
  - Clearly state you're applying a principle when doing so
  - Explain the underlying reasoning from Buffett's philosophy
  - Acknowledge when you're extrapolating from general principles to specific scenarios

HONESTY: If a question falls outside Buffett's documented philosophy, say so honestly and offer the closest relevant principle instead. Be mindful not to guarantee specific investment returns on individual stocks, but you may discuss potential returns based on applying Buffett's investment philosophy and principles.
```

**Configuration:**
- `/chat-api/terraform/environments/dev/variables.tf` (lines 106-136)
- Also updated in `/chat-api/terraform/modules/bedrock/variables.tf` (lines 194-224)

## Deployment Details

### Terraform Changes

**Modified Files:**
1. `/chat-api/terraform/environments/dev/main.tf`
   - Line 266: `enable_prompt_override = false` → `enable_prompt_override = true`

2. `/chat-api/terraform/environments/dev/variables.tf`
   - Lines 100-104: Updated foundation model
   - Lines 106-136: Enhanced agent instructions

3. `/chat-api/terraform/modules/bedrock/variables.tf`
   - Line 191: Updated foundation model default
   - Lines 194-224: Updated agent instruction default
   - Line 279: Updated temperature to 0.3
   - Lines 432-457: Reduced content filter strengths
   - Lines 538-547: Lowered contextual grounding thresholds

### Deployment Commands

```bash
cd /Users/christopherweinreich/Documents/Projects/buffett_chat_api/chat-api/terraform/environments/dev

# 1. Plan changes
terraform plan -out=tfplan

# 2. Apply changes
terraform apply -auto-approve tfplan

# 3. Verify agent status
aws bedrock-agent get-agent --agent-id QTFYZ6BBSE --region us-east-1
```

### Agent Information

- **Agent ID:** `QTFYZ6BBSE`
- **Agent Alias:** `WNW1OMPUEW`
- **Agent Name:** `BuffettGPT-Investment-Advisor-Dev`
- **Region:** `us-east-1`
- **Status:** `PREPARED`
- **Guardrail ID:** `3zsatj11y3vz`
- **Guardrail Version:** `1`

## Verification

### Final Configuration Check

```bash
aws bedrock-agent get-agent --agent-id QTFYZ6BBSE --region us-east-1 | jq '{
  foundationModel: .agent.foundationModel,
  agentStatus: .agent.agentStatus,
  guardrail: .agent.guardrailConfiguration,
  orchestrationTemperature: .agent.promptOverrideConfiguration.promptConfigurations[] | select(.promptType == "ORCHESTRATION") | .inferenceConfiguration.temperature
}'
```

**Expected Output:**
```json
{
  "foundationModel": "anthropic.claude-3-5-haiku-20241022-v1:0",
  "agentStatus": "PREPARED",
  "guardrail": {
    "guardrailIdentifier": "3zsatj11y3vz",
    "guardrailVersion": "1"
  },
  "orchestrationTemperature": 0.30000001192092896
}
```

## Expected Behavior Changes

### User Experience Improvements

1. **More Natural Conversations**
   - Responses will vary slightly in phrasing
   - Less repetitive language
   - More engaging and personable tone

2. **Better Principle Application**
   - Can apply Buffett's principles to modern scenarios
   - More helpful for current investment questions
   - Better synthesis across multiple shareholder letters

3. **Reduced False Rejections**
   - Fewer inappropriate content warnings
   - More permissive with edge-case financial discussions
   - Better handling of complex financial scenarios

4. **Enhanced Financial Guidance**
   - Can discuss potential returns based on Buffett's philosophy
   - More flexible in applying investment principles
   - Better at extrapolating from historical examples

### Maintained Safety Features

- Still grounded in Buffett's shareholder letters
- Won't guarantee specific stock returns
- Maintains content filtering for inappropriate content
- Continues to cite sources when applicable
- Asks clarifying questions for vague queries

## Monitoring Recommendations

### Key Metrics to Watch

1. **Response Quality**
   - Monitor user satisfaction
   - Check for hallucinations or inaccurate advice
   - Verify grounding in source material

2. **Guardrail Triggers**
   - Track how often guardrails block responses
   - Identify false positives
   - Adjust filters if needed

3. **Temperature Impact**
   - Compare response consistency
   - Monitor for excessive variation
   - Verify financial advice remains accurate

### Rollback Plan

If issues arise, revert by:

1. **Disable Prompt Override:**
   ```hcl
   # /chat-api/terraform/environments/dev/main.tf (line 266)
   enable_prompt_override = false
   ```

2. **Revert to Claude 3 Haiku:**
   ```hcl
   # /chat-api/terraform/environments/dev/variables.tf (line 103)
   default = "anthropic.claude-3-haiku-20240307-v1:0"
   ```

3. **Apply Changes:**
   ```bash
   terraform apply -auto-approve
   ```

## Future Optimization Opportunities

### Potential Enhancements

1. **Dynamic Temperature Adjustment**
   - Lower temperature (0.1-0.2) for financial calculations
   - Higher temperature (0.4-0.5) for general philosophy discussions

2. **Custom Prompt Templates**
   - Specialized prompts for different query types
   - Enhanced formatting for complex financial analysis

3. **Enhanced Knowledge Base Integration**
   - More sophisticated retrieval strategies
   - Better ranking of relevant passages

4. **A/B Testing**
   - Compare old vs. new configuration
   - Measure user satisfaction metrics
   - Optimize based on real usage data

### Version Management

Consider creating versioned agent snapshots:
- Tag stable configurations
- Track performance metrics per version
- Enable quick rollback to known-good states

## Conclusion

These optimizations significantly improve the BuffettGPT agent's capabilities while maintaining safety and accuracy. The changes enable more natural, flexible, and helpful financial guidance based on Warren Buffett's investment philosophy.

### Key Takeaways

✅ **Upgraded Model**: Claude 3.5 Haiku provides better reasoning
✅ **Balanced Temperature**: 0.3 adds natural variation
✅ **Less Restrictive**: Lower guardrail thresholds reduce false positives
✅ **More Flexible**: Can apply principles to current scenarios
✅ **Still Safe**: Maintains grounding and content filtering

---

**Document Version:** 1.0
**Date:** October 7, 2025
**Author:** Claude (Anthropic)
**Deployment Status:** ✅ Successfully Deployed to Dev Environment
