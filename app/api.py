# -*- coding: utf-8 -*-
"""api module for wsgi to AWS lambda

See README https://github.com/logandk/serverless-wsgi
"""
import logging
import serverless_wsgi

from sequence_run_manager.wsgi import application

logger = logging.getLogger(__name__)


def handler(event, context):
    """
    Lambda handler with exception logging.

    Logs all exceptions with remaining time for monitoring in CloudWatch.
    """
    try:
        return serverless_wsgi.handle_request(application, event, context)
    except Exception as e:
        # Log all exceptions with remaining time and context info
        remaining_ms = context.get_remaining_time_in_millis()
        remaining_seconds = remaining_ms / 1000.0

        logger.error(
            f"Lambda exception: {remaining_seconds:.2f}s remaining. "
            f"Request ID: {context.aws_request_id}, "
            f"Function: {context.function_name}, "
            f"Log stream: {context.log_stream_name}, "
            f"Error type: {type(e).__name__}, Error: {str(e)}"
        )
        raise
