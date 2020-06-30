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


class LambdaHandler(object):

    MASTER_ACCOUNT_PERMISSIONS_STACK_SET_NAME = 'Dome9AutomaticOnboardingStackSet'
    CUSTOMER_ACCOUNT_EXECUTION_ROLE_NAME = "AWSControlTowerExecution"
    MASTER_ACCOUNT_STACK_SET_ROLE = "service-role/AWSControlTowerStackSetRole"
    STACK_OPERATION_WAIT_RETRIES = 12
    STACK_OPERATION_WAIT_SLEEP = 10

    def __init__(self, region_name: str, customer_account_id: str, customer_account_name: str, readonly: bool = True) -> None:
        logger.info(f'''Init LambdaHandler with region_name: '{region_name}', customer_account_id: '{customer_account_id}', customer_account_name: '{customer_account_name}''''')
        self.region_name = region_name
        self.customer_account_id = customer_account_id
        self.master_account_id = self.retrieve_master_account_id()

        self.customer_account_name = customer_account_name
        self.customer_account_new_role_name = f"Dome9Role-{self.master_account_id}-{self.customer_account_id}"
        self.customer_account_new_role_arn = f"arn:aws:iam::{self.customer_account_id}:role/{self.customer_account_new_role_name}"
        self.customer_account_external_id = self.generate_external_id()

        self.cloudformation_client = boto3.client("cloudformation")
        if readonly:
            self.user_side_stack_cf_filename = "user_side_stack_ro.yaml"
        else:
            self.user_side_stack_cf_filename = "user_side_stack_full.yaml"

    @staticmethod
    def retrieve_master_account_id() -> str:
        """
        Retrieve account running this lambda

        :return: Account name
        """

        sts_client = boto3.client('sts')
        response = sts_client.get_caller_identity()
        return response.get("Account")

    @staticmethod
    def generate_external_id() -> str:
        """
        Generate external id to be used in New Account Dome9 role for trust.

        :return:
        """

        return str(uuid4())[:8]

    def create_stack_set(self) -> Dict:
        """
        Trigger AWS stack set creation.

        :return: Response of the creation command
        """

        administrator_role_arn = f"arn:aws:iam::{self.master_account_id}:role/{self.MASTER_ACCOUNT_STACK_SET_ROLE}"

        logger.info(f"Creating StackSet: {self.MASTER_ACCOUNT_PERMISSIONS_STACK_SET_NAME}, "
                    f"administrator_role_arn : {administrator_role_arn}, "
                    f"customer_account_external_id: {self.customer_account_external_id}, "
                    f"customer_account_new_role_name: {self.customer_account_new_role_name}")

        with open(self.user_side_stack_cf_filename) as f:
            template_body = f.read()

        response = self.cloudformation_client.create_stack_set(
            StackSetName=LambdaHandler.MASTER_ACCOUNT_PERMISSIONS_STACK_SET_NAME,
            Description='Dome9 auto onboarding stack set',
            TemplateBody=template_body,
            Parameters=[{'ParameterKey': 'Externalid', 'ParameterValue': "Placeholder"},
                        {'ParameterKey': 'AccountRoleName', 'ParameterValue': "Placeholder"}],
            Capabilities=[
                'CAPABILITY_IAM', 'CAPABILITY_NAMED_IAM', 'CAPABILITY_AUTO_EXPAND'
            ],
            AdministrationRoleARN=administrator_role_arn,
            ExecutionRoleName=LambdaHandler.CUSTOMER_ACCOUNT_EXECUTION_ROLE_NAME
        )

        return response

    def create_stack_instances(self) -> None:
        """
        Trigger the stack instance creation both on Master side and New Account side.

        :return:
        """
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
        """
        Wait for operation to complete.

        :param operation_id: The operation id to wait for
        :return: None

        """
        for retry_count in range(self.STACK_OPERATION_WAIT_RETRIES):
            response = self.cloudformation_client.describe_stack_set_operation(
                StackSetName=self.MASTER_ACCOUNT_PERMISSIONS_STACK_SET_NAME, OperationId=operation_id)

            if response["StackSetOperation"].get("Status") == "SUCCEEDED":
                return response["StackSetOperation"]["StackSetId"]

            logger.info(f"Current operation status {response['StackSetOperation'].get('Status')}, going to sleep for {self.STACK_OPERATION_WAIT_SLEEP}")
            time.sleep(self.STACK_OPERATION_WAIT_SLEEP)

    def delete_stack_instances(self) -> Dict:
        """
        Delete the stack instance.

        :return: Response of the aws deletion command.
        """

        logger.info(f"Deleting stack instance for StackSet: {self.MASTER_ACCOUNT_PERMISSIONS_STACK_SET_NAME}, "
                    f"region: {self.region_name}, AccountId: {self.customer_account_id}")

        response = self.cloudformation_client.delete_stack_instances(StackSetName=self.MASTER_ACCOUNT_PERMISSIONS_STACK_SET_NAME,
                                                                Regions=[self.region_name], RetainStacks=True,
                                                                Accounts=[self.customer_account_id])
        return response

    def delete_stack_set(self) -> Dict:
        """
        Delete the stack set

        :return: Response of the delete command.
        """

        logger.info(f"Deleting StackSet: {self.MASTER_ACCOUNT_PERMISSIONS_STACK_SET_NAME}")
        return self.cloudformation_client.delete_stack_set(StackSetName=self.MASTER_ACCOUNT_PERMISSIONS_STACK_SET_NAME)

    def register_to_dome9(self) -> Dict:
        """
        Make API request to dome9 to lunch the onboarding.

        :return: Response from Dome9 API
        """

        dome9_client = Client()
        credentials = CloudAccountCredentials(arn=self.customer_account_new_role_arn, secret=self.customer_account_external_id)
        payload = CloudAccount(name=self.customer_account_name, credentials=credentials)
        resp = dome9_client.aws_cloud_account.create(body=payload)
        return resp

    def create_stack_set_flow(self) -> None:
        """
        Handle stack set creation

        :return:
        """

        try:
            self.create_stack_set()
        except Exception as e:
            if "NameAlreadyExistsException" in repr(e):
                logger.info(f"Received NameAlreadyExistsException for stack_set '{self.MASTER_ACCOUNT_PERMISSIONS_STACK_SET_NAME}'. Error: {repr(e)}")
                self.delete_stack_instances()
                time.sleep(20)
            else:
                raise

    def execute_onboarding_flow(self) -> Dict:
        """
        Execute the whole onboarding process.

        :return:
        """

        self.create_stack_set_flow()
        self.create_stack_instances()
        time.sleep(20)
        register_result = self.register_to_dome9()
        return register_result


def lambda_handler(event: Dict, context: Dict) -> Dict:
    """
    Makes the magic happen.
    Creates Dome9 protected account:
    1) Creates needed infrastructure on the New Account's side.
    2) Triggers automatic onboardig.

    :param event: AWS lambda event
    :param context: AWS lambda context
    :return: Status
    """

    logger.info(f"Event: {event}")
    logger.info(f"Context: {context}")

    event = event["detail"]

    logger.info(f"Event reported state: {event['serviceEventDetails']['createManagedAccountStatus']['state']}'")
    lmb_handler = LambdaHandler(event["awsRegion"], event["serviceEventDetails"]["createManagedAccountStatus"]["account"]["accountId"], event["serviceEventDetails"]["createManagedAccountStatus"]["account"]["accountName"])
    onboarding_result = lmb_handler.execute_onboarding_flow()

    return {
        'statusCode': 200,
        'body': json.dumps(f'{onboarding_result} Created stack-set')
    }

