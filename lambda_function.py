import json
import boto3
import time
import logging
import base64

from dome9_type_annotations.client import Client
from resources.aws_cloud_account import CloudAccount, CloudAccountCredentials
from uuid import uuid4
from typing import Dict

logger = logging.getLogger()
logger.setLevel(logging.INFO)


class OperationFailedError(Exception):
    pass


class LambdaHandler(object):
    MASTER_ACCOUNT_PERMISSIONS_STACK_SET_NAME = 'Dome9AutomaticOnboardingStackSet'
    CUSTOMER_ACCOUNT_EXECUTION_ROLE_NAME = "AWSControlTowerExecution"
    MASTER_ACCOUNT_STACK_SET_ROLE = "service-role/AWSControlTowerStackSetRole"
    STACK_OPERATION_WAIT_RETRIES = 60  # 5 minutes
    STACK_OPERATION_WAIT_SLEEP = 5
    DOME9_SECRET_NAME = "Dome9ApiKeys"

    def __init__(self, region_name: str, customer_account_id: str, customer_account_name: str,
                 readonly: bool = True) -> None:

        logger.info(f"Init LambdaHandler with region_name: '{region_name}', "
                    f"customer_account_id: '{customer_account_id}', customer_account_name: '{customer_account_name}'")

        if not customer_account_id.isnumeric():
            raise ValueError(f"Customer Account ID should be Numeric value. E.g. '12345678'. Received: {str(customer_account_id)}")

        self.region_name = region_name
        self.customer_account_id = customer_account_id
        self.master_account_id = self.retrieve_master_account_id()

        self.customer_account_name = customer_account_name
        self.customer_account_new_role_name = f"Dome9Role-{self.master_account_id}-{self.customer_account_id}"
        self.customer_account_new_role_arn = f"arn:aws:iam::{self.customer_account_id}:role/{self.customer_account_new_role_name}"
        self.customer_account_external_id = self.generate_external_id()

        # Create a CloudFormation client
        self.cloudformation_client = boto3.client(
            service_name="cloudformation",
            region_name=self.region_name)
        # Create a Secrets Manager client
        self.secret_manager_client = boto3.client(
            service_name='secretsmanager',
            region_name=self.region_name)

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

        sts_client = boto3.client("sts")
        response = sts_client.get_caller_identity()
        return response.get("Account")

    @staticmethod
    def generate_external_id() -> str:
        """
        Generate external id to be used in New Account Dome9 role for trust.

        :return:
        """

        return str(uuid4())[:8]

    def get_secret(self) -> Dict:
        """
        Get Dome9 AccessId and Secret for API authentication

        :return:
        """

        try:
            logger.info("Getting Dome9 API credentials from AWS SecretManager")
            secret_value_response = self.secret_manager_client.get_secret_value(
                SecretId=LambdaHandler.DOME9_SECRET_NAME
            )
        except Exception as e:
            logger.error(f"Could not get secret value for SecretId: {LambdaHandler.DOME9_SECRET_NAME}")
            raise
        else:
            if 'SecretString' in secret_value_response:
                secret = secret_value_response['SecretString']
                return json.loads(secret)
            
            decoded_binary_secret = base64.b64decode(secret_value_response['SecretBinary'])
            return json.loads(decoded_binary_secret)

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
            Description="Dome9 auto onboarding stack set",
            TemplateBody=template_body,
            Parameters=[{"ParameterKey": "Externalid", "ParameterValue": "Placeholder"},
                        {"ParameterKey": "AccountRoleName", "ParameterValue": "Placeholder"}],
            Capabilities=[
                "CAPABILITY_IAM", "CAPABILITY_NAMED_IAM", "CAPABILITY_AUTO_EXPAND"],
            AdministrationRoleARN=administrator_role_arn,
            ExecutionRoleName=LambdaHandler.CUSTOMER_ACCOUNT_EXECUTION_ROLE_NAME)
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
            ParameterOverrides=[
                {"ParameterKey": "AccountRoleName", "ParameterValue": self.customer_account_new_role_name},
                {"ParameterKey": "Externalid", "ParameterValue": self.customer_account_external_id}],
            OperationPreferences={
                "FailureToleranceCount": 0,
                "MaxConcurrentCount": 3,
            })

        self.wait_for_stack_operation(response["OperationId"], "create_stack_instances")

    def wait_for_stack_operation(self, operation_id: str, operation_name: str) -> None:
        """
        Wait for operation to complete.

        :param operation_name: Name used for logging
        :param operation_id: The operation id to wait for
        :return: None

        """

        for retry_count in range(self.STACK_OPERATION_WAIT_RETRIES):
            current_status = "FAILED_TO_FETCH"
            try:
                response = self.cloudformation_client.describe_stack_set_operation(
                    StackSetName=self.MASTER_ACCOUNT_PERMISSIONS_STACK_SET_NAME, OperationId=operation_id)
                current_status = response.get('StackSetOperation').get('Status')
            except Exception as e:
                logger.error(f"Failed to fetch operation's {operation_name} status {current_status}")

            logger.info(f"Current operation: '{operation_name}' Status: {current_status}")

            if current_status == "SUCCEEDED":
                return
            elif current_status == "FAILED":
                raise OperationFailedError(f"Operation {operation_name} failed to complete! "
                                           f"Check 'cloudformation' StackSet '{self.MASTER_ACCOUNT_PERMISSIONS_STACK_SET_NAME}' for more information")

            logger.info(f"Going to sleep for {self.STACK_OPERATION_WAIT_SLEEP} seconds")

            time.sleep(self.STACK_OPERATION_WAIT_SLEEP)

    def delete_stack_instances(self) -> None:
        """
        Delete the stack instance.

        :return: Response of the aws deletion command.
        """

        logger.info(f"Deleting stack instance for StackSet: {self.MASTER_ACCOUNT_PERMISSIONS_STACK_SET_NAME}, "
                    f"region: {self.region_name}, AccountId: {self.customer_account_id}")

        try:
            response = self.cloudformation_client.delete_stack_instances(
                StackSetName=self.MASTER_ACCOUNT_PERMISSIONS_STACK_SET_NAME,
                Regions=[self.region_name], RetainStacks=False,
                Accounts=[self.customer_account_id])
        except Exception as e:
            logger.warning(f"Stack instance deletion failed with error: {repr(e)}. "
                           f"Possibly this stack instance already exists.")
            return

        self.wait_for_stack_operation(response.get("OperationId"), "delete_stack_instances")

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
        dome9_api_keys = self.get_secret()
        dome9_client = Client(access_id=dome9_api_keys['AccessId'], secret_key=dome9_api_keys['Secret'])
        credentials = CloudAccountCredentials(arn=self.customer_account_new_role_arn,
                                              secret=self.customer_account_external_id)
        payload = CloudAccount(name=self.customer_account_name, credentials=credentials)
        response = dome9_client.aws_cloud_account.create(body=payload)
        logger.info(f"Received reply from dome9 API: {response}")

        return response

    def create_stack_set_flow(self) -> None:
        """
        Handle stack set creation

        :return:
        """

        try:
            self.create_stack_set()
            logger.info(f"StackSet '{self.MASTER_ACCOUNT_PERMISSIONS_STACK_SET_NAME}' created")
        except Exception as e:
            repr_e_lower = repr(e).lower()
            if "already" in repr_e_lower and "exists" in repr_e_lower:
                logger.warning(
                    f"StackSet '{self.MASTER_ACCOUNT_PERMISSIONS_STACK_SET_NAME}' already exists. Skipping this step.")
                self.delete_stack_instances()
            else:
                raise

    def execute_onboarding_flow(self) -> Dict:
        """
        Execute the whole onboarding process.

        :return:
        """

        self.create_stack_set_flow()
        self.create_stack_instances()
        try:
            register_result = self.register_to_dome9()
            return {"Status": f"Onboarding finished. Received reply from Dome9: {str(register_result)}"}
        except Exception as e:
            logger.error(f"An error '{repr(e)}' occurred in the onboarding process. Aborting the flow. "
                         f"Going to delete the StackInstance")
            self.delete_stack_instances()

        return {"Status": "Failure"}

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

    event = event["detail"]
    event_state = event["serviceEventDetails"]["createManagedAccountStatus"]["state"]
    aws_region = event["awsRegion"]
    new_account_id = event["serviceEventDetails"]["createManagedAccountStatus"]["account"]["accountId"]
    new_account_name = event["serviceEventDetails"]["createManagedAccountStatus"]["account"]["accountName"]

    logger.info(f"Triggered by ControlTower event. Event correct state: 'SUCCESS'. Reported state: '{event_state}'")

    lmb_handler = LambdaHandler(aws_region, new_account_id, new_account_name)

    onboarding_result = lmb_handler.execute_onboarding_flow()

    return {
        "statusCode": 200,
        "body": json.dumps(f"{onboarding_result} Created stack-set")
    }

