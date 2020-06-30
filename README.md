![Dome9 Logo](https://dome9.com/wp-content/uploads/2018/12/Dome9_Grey.png)

# CloudGuard Dome9 Automatic onboarding application
Source code for AWS serverless application to automatically onboard AWS account to Dome9 when a new account is created using AWS ControlTower service

## Prerequisites
- [ControlTower](https://aws.amazon.com/controltower/) properly installed in root account. 
- CloudGuard Dome9 account. You sign up [here](https://secure.dome9.com/).

## What's included
- Lambda function for onboarding automation
- EventBridge rule (configured to "listen" to `CreateMenagedAccount` lifecycle event)
- CloudWatch Alarm (lambda failures)
- SNS topic for email notifications (subscription confirmation email will be sent)

## Installation with AWS Console
1. Generate CloudGuard Dome9 API keys. You can find the instructions [here](https://supportcenter.checkpoint.com/supportcenter/portal?eventSubmit_doGoviewsolutiondetails=&solutionid=sk144514&partition=General&product=CloudGuard)
2. Login to your AWS Console
3. Navigate to Lambda -> Create Function
4. Select "Browse serverless app repository option"
5. Type "dome9" and the search text box and make sure that "Show apps that create custom IAM roles or resource policies" is selected
6. Select the application "dome9-automatic-onboarding"
3. Fill the required fields `Dome9AccessId` and `Dome9SecretKey` with you keys from the previous step.
4. Fill the `NotificationEmail` field. Any onboarding failures will be sent to this address
5. Check all the checkboxes under `Capabilities and transforms`