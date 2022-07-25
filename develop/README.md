
# For Developers
Welcome, we are happy you joint us (Dome9 SRE team)

## Makefile examples:
Source code for AWS serverless application to automatically onboard AWS accounts to CloudGuard Dome9 when a new account is created, using the AWS Control Tower service.

## AWS Console
Cloudwatch create managed account event lookup:
{ $.eventName = "CreateManagedAccount" }

CloudWatch -> CloudWatch Logs -> Log groups -> aws-controltower/CloudTrailLogs -> <you-master-account-id>_CloudTrail_<your-region>

## Publishing the ServerLess Application
1. Run pip install -r requirements.txt, to install all the lambda requirements.
2. Follow the aws step tp [publish ServerLess Application Using the Cli](https://docs.aws.amazon.com/serverless-application-model/latest/developerguide/serverless-sam-template-publishing-applications.html)
3. Test the lambda by creating the lambda under an onboarded aws account, then go to Account Factory and create an account, you will get an email and the account must be onboarded automatically.