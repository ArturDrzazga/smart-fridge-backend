from celery import shared_task
import logging


logger = logging.getLogger(__name__)

@shared_task
def add_test_task(x, y):
    result = x + y

    logger.info(f"--- Celery Test Task: {x} + {y} = {result} ---")
    return result