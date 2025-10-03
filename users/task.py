from celery import shared_task

@shared_task
def send_welcome_email(user_id):
    # send email
    return True
