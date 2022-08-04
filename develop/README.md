
# For Developers
Welcome, we are happy you joint us (Dome9 SRE team)

## Makefile examples:
Source code for AWS serverless application to automatically onboard AWS accounts to CloudGuard Dome9 when a new account is created, using the AWS Control Tower service.

## AWS Console
Cloudwatch create managed account event lookup:
{ $.eventName = "CreateManagedAccount" }

CloudWatch -> CloudWatch Logs -> Log groups -> aws-controltower/CloudTrailLogs -> <you-master-account-id>_CloudTrail_<your-region>

## Publishing the ServerLess Application
1. Install Python 3.7.x > 3.7.0
2. Install AWS CLI
3. Install AWS SAM CLI
4. Create AWS Credential(Key+Password) in your AWS account
5. Setup AWS Credential file profile locally
6. Install Docker
7. Run in the CMD under the project dir, make sure to adjust some parameter according to your case(Take a look at MakeFile)
   1. `pip install -r requirements.txt`
   2. `sam build --use-container`
   3. `sam local invoke Dome9AutomationLambda --event ./develop/event_account_creation.json` (It is optional to run, and it tests if the lambda is build correctly)
   4. `sam package --template-file .aws-sam/build/template.yaml --output-template-file .aws-sam/build/packaged.yaml --s3-bucket cloudguard-cloudtower-integration-sam-template --profile serverless-repo-account --region us-east-1`
      1. cloudguard-cloudtower-integration-sam-template is the default S3 bucket
      2. serverless-repo-account is the AWS profile name configured in step:5
   5. `sam publish --template .aws-sam/build/packaged.yaml --region us-east-1 --profile serverless-repo-account`
8. Test the lambda:
   1. Create the lambda under an onboarded aws account
      1. Take a look at the main README
   2. Search for Control Tower and go to Account Factory 
   3. create an account, you will get an email and the account must be onboarded automatically.