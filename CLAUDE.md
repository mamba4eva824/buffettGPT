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
