# handler/trigger_backup.py
import boto3
import json
import logging
import time
import os

logger = logging.getLogger()
logger.setLevel(logging.INFO)


def handler(event, context):
    try:
        stepfunctions = boto3.client('stepfunctions')

        response = stepfunctions.start_execution(
            stateMachineArn=os.environ['STATE_MACHINE_ARN'],
            input=json.dumps({})
        )

        execution_arn = response['executionArn']
        logger.info(f"Backup Step Function started: {execution_arn}")

        # Sleep for 1 minute initially
        logger.info("Waiting 45 seconds before checking status...")
        time.sleep(45)

        # Poll for completion every 10 seconds
        while True:

            # Check execution status
            status_response = stepfunctions.describe_execution(
                executionArn=execution_arn)
            status = status_response['status']

            logger.info(f"Step Function status: {status}")

            if status == 'SUCCEEDED':
                logger.info("Backup completed successfully")
                return {
                    'statusCode': 200,
                    'message': 'Backup completed successfully',
                    'executionArn': execution_arn
                }
            elif status in ['RUNNING']:
                logger.info("Backup still running, waiting 10 seconds...")
                time.sleep(10)  # Wait 10 seconds before checking again
            else:
                error_msg = f"Backup failed with status: {status}"
                if 'error' in status_response:
                    error_msg += f" - {status_response['error']}"
                logger.error(error_msg)
                raise Exception(error_msg)

    except Exception as e:
        logger.error(f"Failed to trigger or monitor backup: {e}")
        raise
