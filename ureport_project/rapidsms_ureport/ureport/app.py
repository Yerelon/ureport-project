import logging
import datetime
from django.core.mail import send_mail
from rapidsms.apps.base import AppBase
from contact.models import Flag, MessageFlag
from poll.models import Poll
from django.db.models import Q
from script.models import Script, ScriptProgress
from rapidsms.models import Contact
import re
from django.conf import settings
from ureport.models import MessageAttribute, MessageDetail, Settings
from .utils import get_language, get_scripts, all_optin_words

from django.core.mail import EmailMessage

from django.contrib.auth.models import Group, User

WORD_TEMPLATE = r"(.*\b(%s)\b.*)"

class App(AppBase):
    def handle (self, message):
        language = get_language(message)
        scripts = get_scripts()

        #dump new connections in Autoreg
        if not message.connection.contact and not\
        ScriptProgress.objects.filter(script__slug__in=scripts, connection=message.connection).exists():

            #use the detected language to dump the user in the right script
            lang_scripts = settings.SCRIPTS
            prog = ScriptProgress.objects.create(script = Script.objects.get(pk = lang_scripts[language][1]), connection = message.connection)
            prog.language = language
            prog.save()

        #registering twice should not be allowed, user is informed
        elif message.text.lower().strip() in all_optin_words():
            message.respond(getattr(settings,'OPTED_IN_CONFIRMATION','')[language])
            return True

        #message flagging sfuff
        else:
            #alerts (needs further investigations)
            if message.connection.contact:
                alert_setting, _ = Settings.objects.get_or_create(attribute = "alerts")
                if alert_setting.value == "true":
                    alert, _ = MessageAttribute.objects.get_or_create(name = "alert")
                    msg_a = MessageDetail.objects.create(message = message.db_message, attribute = alert, value = 'true')

            #user can toggle their preferred language
            for lang, lang_verbose in getattr(settings, 'LANGUAGES', None):
                if message.connection.contact and message.text.lower() == lang:
                    contact = message.connection.contact
                    contact.language = lang
                    contact.save()
                    message.respond(getattr(settings,'LANGUAGE_CHANGE_CONFIRMATION','')[lang])
                    return True

        #message flagging (needs further investigation)
        flags = Flag.objects.exclude(rule = None).exclude(rule_regex = None)
        pattern_list = [[re.compile(flag.rule_regex, re.I), flag] for flag in flags if flag.rule ]
        for reg in pattern_list:
            match = reg[0].search(message.text)
            import ipdb; ipdb.set_trace()
            if match:
                if hasattr(message, 'db_message'):
                    msg = message.db_message
                else:
                    msg = message
                mf = MessageFlag.objects.create(message = msg,flag = reg[1])
                #alert_group = Group.objects.get_or_create(name="alert_%s" % reg[1])
                #for user_to_alert in alert_group.user_set.all():
                    #if user_to_alert.mail:
                        #send_mail('A u-reporter with ID %s Sent Message to Ureport' % message.connection_id , message.text, "Ureport #Alerts<alerts@unicefburundi.bi>",[user_to_alert.mail], fail_silently=True)
                print mf

                alert_group = Group.objects.get(name="alert_%s"%(reg[1].name))
                if alert_group :
                    alert_users = User.objects.filter(groups__name = alert_group.name)
                    for user in alert_users:
                        if user.email:
                            print(user.email)
                            email_adress = "%s" % user.email
                            email = EmailMessage('The object', 'The content', to=[email_adress])
                            email.send()


        #if no rule_regex default to name this is just for backward compatibility ... it will soon die an unnatural death

        flags = Flag.objects.filter(rule = None).values_list('name', flat = True).distinct()

        w_regex = []
        for word in flags:
            w_regex.append(WORD_TEMPLATE % re.escape(str(word).strip()))
        reg = re.compile(r"|".join(w_regex), re.I)
        match = reg.search(message.text)
        if match:
            #we assume ureport is not the first sms app in the list so there is no need to create db_message
            if hasattr(message, 'db_message'):
                db_message = message.db_message
                try:
                    flag = Flag.objects.get(name=[d for d in list(match.groups()) if d][1])
                except (Flag.DoesNotExist, IndexError):
                    flag = None

                MessageFlag.objects.create(message = db_message, flag=flag)

        return False

