import json
import boto3
import time
import logging

from dome9_type_annotations.client import Client
from resources.aws_cloud_account import CloudAccount, CloudAccountCredentials
from uuid import uuid4
from typing import Dict

logger = logging.getLogger()
logger.setLevel(logging.INFO)


class Onboarder(object):

    MASTER_ACCOUNT_PERMISSIONS_STACK_SET_NAME = 'Dome9AutomaticOnboardigStackSet'
    CUSTOMER_ACCOUNT_EXECUTION_ROLE_NAME = "AWSControlTowerExecution"
    MASTER_ACCOUNT_STACK_SET_ROLE = "service-role/AWSControlTowerStackSetRole"
    STACK_OPERATION_WAIT_RETRIES = 12
    STACK_OPERATION_WAIT_SLEEP = 10

    def __init__(self, region_name: str, customer_account_id: str, customer_account_name: str, readonly: bool = True) -> None:
        logger.info(f"Initing onboarder with region_name: '{region_name}', customer_account_id: '{customer_account_id}', customer_account_name: '{customer_account_name}'")
        self.region_name = region_name
        self.customer_account_id = customer_account_id
        self.master_account_id = self.retrieve_master_account_id()

        self.customer_account_name = customer_account_name
        self.customer_account_new_role_name = f"Dome9Role-{self.master_account_id}-{self.customer_account_id}"
        self.customer_account_new_role_arn = f"arn:aws:iam::{self.customer_account_id}:role/{self.customer_account_new_role_name}"
        self.customer_account_external_id = self.generate_external_id()

        self.cloudformation_client = boto3.client("cloudformation")
        if readonly:
            self.user_side_stack_cf_filename = "user_side_stack.yaml"
        else:
            self.user_side_stack_cf_filename = "user_side_stack.yaml"

    @staticmethod
    def retrieve_master_account_id() -> str:
        sts_client = boto3.client('sts')
        response = sts_client.get_caller_identity()
        return response.get("Account")

    @staticmethod
    def generate_external_id() -> str:
        return str(uuid4())[:8]

    def create_stack_set(self) -> Dict:
        administrator_role_arn = f"arn:aws:iam::{self.master_account_id}:role/{self.MASTER_ACCOUNT_STACK_SET_ROLE}"

        logger.info(f"Creating StackSet: {self.MASTER_ACCOUNT_PERMISSIONS_STACK_SET_NAME}, "
                    f"administrator_role_arn : {administrator_role_arn}, "
                    f"customer_account_external_id: {self.customer_account_external_id}, "
                    f"customer_account_new_role_name: {self.customer_account_new_role_name}")

        with open(self.user_side_stack_cf_filename) as f:
            template_body = f.read()

        response = self.cloudformation_client.create_stack_set(
            StackSetName=Onboarder.MASTER_ACCOUNT_PERMISSIONS_STACK_SET_NAME,
            Description='Dome9 auto onboarding stack set',
            TemplateBody=template_body,
            Parameters=[{'ParameterKey': 'Externalid', 'ParameterValue': "Placeholder"},
                        {'ParameterKey': 'AccountRoleName', 'ParameterValue': "Placeholder"}],
            Capabilities=[
                'CAPABILITY_IAM', 'CAPABILITY_NAMED_IAM', 'CAPABILITY_AUTO_EXPAND'
            ],
            AdministrationRoleARN=administrator_role_arn,
            ExecutionRoleName=Onboarder.CUSTOMER_ACCOUNT_EXECUTION_ROLE_NAME
        )

        return response

    def create_stack_instances(self) -> None:
        logger.info(f"Creating stack instance for StackSet: {self.MASTER_ACCOUNT_PERMISSIONS_STACK_SET_NAME}, "
                    f"region: {self.region_name}, AccountId: {self.customer_account_id}, "
                    f"NewRoleName {self.customer_account_new_role_name}")

        response = self.cloudformation_client.create_stack_instances(
            StackSetName=self.MASTER_ACCOUNT_PERMISSIONS_STACK_SET_NAME,
            Accounts=[self.customer_account_id],
            Regions=[self.region_name],
            ParameterOverrides=[{'ParameterKey': 'AccountRoleName', 'ParameterValue': self.customer_account_new_role_name},
                                {'ParameterKey': 'Externalid', 'ParameterValue': self.customer_account_external_id}],
            OperationPreferences={
                'FailureToleranceCount': 0,
                'MaxConcurrentCount': 3,
            })

        self.wait_for_stack_operation(response["OperationId"])

    def wait_for_stack_operation(self, operation_id: str) -> None:
        for retry_count in range(self.STACK_OPERATION_WAIT_RETRIES):
            response = self.cloudformation_client.describe_stack_set_operation(
                StackSetName=self.MASTER_ACCOUNT_PERMISSIONS_STACK_SET_NAME, OperationId=operation_id)

            if response["StackSetOperation"].get("Status") == "SUCCEEDED":
                return response["StackSetOperation"]["StackSetId"]

            logger.info(f"Current operation status {response['StackSetOperation'].get('Status')}, going to sleep for {self.STACK_OPERATION_WAIT_SLEEP}")
            time.sleep(self.STACK_OPERATION_WAIT_SLEEP)

    def delete_stack_instances(self) -> Dict:
        logger.info(f"Deleting stack instance for StackSet: {self.MASTER_ACCOUNT_PERMISSIONS_STACK_SET_NAME}, "
                    f"region: {self.region_name}, AccountId: {self.customer_account_id}")

        response = self.cloudformation_client.delete_stack_instances(StackSetName=self.MASTER_ACCOUNT_PERMISSIONS_STACK_SET_NAME,
                                                                Regions=[self.region_name], RetainStacks=True,
                                                                Accounts=[self.customer_account_id])
        return response

    def delete_stack_set(self):
        logger.info(f"Deleting StackSet: {self.MASTER_ACCOUNT_PERMISSIONS_STACK_SET_NAME}")
        return self.cloudformation_client.delete_stack_set(StackSetName=self.MASTER_ACCOUNT_PERMISSIONS_STACK_SET_NAME)

    def register_to_dome9(self) -> Dict:
        dome9_client = Client()
        credentials = CloudAccountCredentials(arn=self.customer_account_new_role_arn, secret=self.customer_account_external_id)
        payload = CloudAccount(name=self.customer_account_name, credentials=credentials)
        resp = dome9_client.aws_cloud_account.create(body=payload)
        return resp

    def create_stack_set_flow(self) -> None:
        try:
            self.create_stack_set()
        except Exception as e:
            if "NameAlreadyExistsException" in repr(e):
                logger.info(f"Received NameAlreadyExistsException for stack_set '{self.MASTER_ACCOUNT_PERMISSIONS_STACK_SET_NAME}'. Error: {repr(e)}")
                self.delete_stack_instances()
                time.sleep(20)
                #self.delete_stack_set()
                #time.sleep(30)
                #self.create_stack_set()
            else:
                raise

    def execute_onboarding_flow(self):
        self.create_stack_set_flow()
        self.create_stack_instances()
        time.sleep(20)
        register_result = self.register_to_dome9()
        return register_result


def lambda_handler(event, context):
    logger.info(f"Event: {event}")
    logger.info(f"Context: {context}")

    event = event["detail"]

    logger.info(f"Event reported state: {event['serviceEventDetails']['createManagedAccountStatus']['state']}'")
    onboarder = Onboarder(event["awsRegion"], event["serviceEventDetails"]["createManagedAccountStatus"]["account"]["accountId"], event["serviceEventDetails"]["createManagedAccountStatus"]["account"]["accountName"])
    onboarding_result = onboarder.execute_onboarding_flow()

    return {
        'statusCode': 200,
        'body': json.dumps(f'{onboarding_result} Created stack-set')
    }

