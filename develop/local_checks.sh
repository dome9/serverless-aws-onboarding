




sam build --profile control-tower-integration-alexey

sam local invoke Dome9AutomationLambda --event ./event_account_creation.json


sam package --template-file template.yaml --output-template-file packaged.yaml --s3-bucket test-control-tower-integration --profile control-tower-integration-alexey

sam publish     --template packaged.yaml     --region us-east-1 --profile control-tower-integration-alexey













