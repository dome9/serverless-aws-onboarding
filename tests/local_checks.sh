



sam package --template-file template.yaml --output-template-file packaged.yaml --s3-bucket test-control-tower-integration --profile control-tower-integration-alexey

#build local
sam build

sam local invoke Dome9AutomationLambda --event ./event_account_creation.json

