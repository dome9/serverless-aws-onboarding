PROJECT_DIR=..
SAM_DIR=.aws-sam
INPUT_TEMPLATE=${PROJECT_DIR}/template.yaml
BUILT_TEMPLATE=${SAM_DIR}/build/template.yaml
PACKAGED_FILE=${SAM_DIR}/build/packaged.yaml
S3_BUCKET_NAME=test-control-tower-integration
AWS_REGION=us-east-1
PROFILE=control-tower-integration

# Package and deploy the application
publish:
	sam build --template-file ${INPUT_TEMPLATE} --profile ${PROFILE} --use-container
	sam package --template-file ${BUILT_TEMPLATE} --output-template-file ${PACKAGED_FILE} --s3-bucket ${S3_BUCKET_NAME} --profile ${PROFILE}
	sam publish --template ${PACKAGED_FILE} --region  ${AWS_REGION} --profile ${PROFILE}

clear:
	rm -rf ${SAM_DIR}/*
	rmdir ${SAM_DIR}
