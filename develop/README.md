
# For Developers
Welcome, we are happy you joint us (Dome9 SRE team)

## Makefile examples:
Source code for AWS serverless application to automatically onboard AWS accounts to CloudGuard Dome9 when a new account is created, using the AWS Control Tower service.

## AWS Console
Cloudwatch create managed account event lookup:
{ $.eventName = "CreateManagedAccount" }

CloudWatch -> CloudWatch Logs -> Log groups -> aws-controltower/CloudTrailLogs -> <you-master-account-id>_CloudTrail_<your-region>

