import threading

from email_logger.models import log_emails

from django.core.mail import EmailMessage


class EmailThread(threading.Thread):
    def __init__(self, subject, message, recipient_list):
        self.subject = subject
        self.recipient_list = recipient_list
        self.message = message
        threading.Thread.__init__(self)

    def run(self):
        msg = EmailMessage(self.subject, self.message, to=self.recipient_list)
        msg.content_subtype = "html"
        email_log = log_emails("to real", [msg])[0]
        try:
            msg.send()
        except Exception as e:
            email_log.success = False
            email_log.save()
            raise e


def spawn_send_html_mail(subject, message, recipient_list):
    EmailThread(subject, message, recipient_list).start()
