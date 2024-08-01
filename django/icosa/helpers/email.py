import threading

from django.core.mail import EmailMessage


class EmailThread(threading.Thread):
    def __init__(self, subject, message, recipient_list):
        self.subject = subject
        self.recipient_list = recipient_list
        self.message = message
        threading.Thread.__init__(self)

    def run(self):
        msg = EmailMessage(self.subject, self.message, to=self.recipient_list)
        msg.send()


def spawn_send_html_mail(subject, message, recipient_list):
    EmailThread(subject, message, recipient_list).start()
