![Dome9 Logo](https://central.dome9.com/assets/images/cloud-guard/cloud-guard-logo.svg)

# CloudGuard Automatic onboarding application
Source code for AWS serverless application to automatically onboard AWS accounts to CloudGuard when a new account is created, using the AWS Control Tower service.

## Prerequisites
- [ControlTower](https://aws.amazon.com/controltower/) properly installed in root account. 
- CloudGuard account  (as a user with All System Resources permission). Sign up [here](https://secure.dome9.com/).

## What's included
- Lambda function for onboarding automation
- EventBridge rule (configured to "listen" to `CreateMenagedAccount` lifecycle event)
- Secret Manager's secret for storing API credentials 
- CloudWatch Alarm (lambda failures)
- SNS topic for email notifications (subscription confirmation email will be sent)

## Installation from the AWS Console
1. Generate CloudGuard API keys - in one of two ways:
  1.1. Go to Settings -> Credentials -> Click CREATE API.
  1.2. Go to Settings -> Service Accounts -> Click Add Account and give it OnBoarding role or SuperUser role.
  You can follow instructions [here](https://supportcenter.checkpoint.com/supportcenter/portal?eventSubmit_doGoviewsolutiondetails=&solutionid=sk144514&partition=General&product=CloudGuard).
2. Login to the AWS Console.
3. Navigate to Lambda -> Create Function.
4. Select "Browse serverless app repository option"
5. Check the "Show apps that create custom IAM roles or resource policies".
6. Enter `CloudGuard` inside the search input. 
7. Click  "cloudguard-automatic-onboarding".
8. Enter the required fields `Dome9AccessId` .and `Dome9SecretKey` with you keys from previous steps.
9. Enter an email address in the `NotificationEmail` field. Any onboarding failures will be sent to this address.
10. Check the `I acknowledge that this app creates custom IAM roles.` (If it appears). 
11. Check all the checkboxes under `Capabilities and transforms` (If they appear).
