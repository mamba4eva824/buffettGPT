# MANDATORY DEPLOYMENT RULES

## 🚨 CRITICAL: TERRAFORM DEPLOYMENT ENFORCEMENT

**ABSOLUTE RULE**: ALL infrastructure changes to dev environment MUST use Terraform. 

### Required Terraform Workflow:
1. **Infrastructure as Code** → All changes must be in `.tf` files
2. **Plan before Apply** → Always run `terraform plan` first
3. **State Management** → Use remote state backend
4. **Validation** → Run `terraform validate` before deployment

### Prohibited Actions:
- ❌ Direct AWS console changes
- ❌ Manual resource creation
- ❌ Bypassing Terraform workflows
- ❌ Applying without planning

### Mandatory Commands for Dev Deployment:

```bash
cd chat-api/terraform/environments/dev
terraform init
terraform validate
terraform plan
```

### 🔐 STATE LOCK MANAGEMENT

**CRITICAL**: Before triggering CI/CD pipeline, ensure no local Terraform state locks exist.

If you ran `terraform plan` locally, you MUST release the state lock before pushing to trigger CI/CD:

```bash
# Check if a lock exists (will show lock info if present)
cd chat-api/terraform/environments/dev

# If CI/CD fails with "Error acquiring the state lock", release it:
terraform force-unlock -force <LOCK_ID>
```

**Why this matters**: Local `terraform plan` creates a DynamoDB state lock. If not released, CI/CD pipeline will fail with `ConditionalCheckFailedException`.

**Prevention**: Always ensure local terraform operations complete cleanly before triggering CI/CD.

## 📦 LAMBDA PACKAGING RULES

**ABSOLUTE RULE**: ALL Lambda deployment packages (.zip files) MUST be placed in:
```
chat-api/backend/build/
```

### Lambda Build Requirements:
1. **Build Directory** → All .zip files go to `chat-api/backend/build/`
2. **Package Structure** → Maintain consistent packaging format
3. **Dependencies** → Include all required dependencies in package
4. **Cleanup** → Remove old builds before creating new ones

### Build Directory Structure:
```
chat-api/backend/build/
├── lambda-function-1.zip
├── lambda-function-2.zip
└── lambda-function-n.zip
```
