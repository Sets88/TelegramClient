# -*- coding: utf8 -*-

import os
import sys
import asyncio
from random import choice
from telethon import TelegramClient
from telethon.tl.types import MessageActionChatAddUser
from telethon.tl.functions.messages import GetAllStickersRequest
from telethon.tl.functions.messages import GetStickerSetRequest
from telethon.tl.types import InputStickerSetID
from operator import attrgetter
from time import sleep
import traceback
from datetime import timedelta, datetime


API_ID = os.environ['TG_API_ID']
API_HASH = os.environ['TG_API_HASH']
PHONE = os.environ['TG_PHONE']
USERNAME = os.environ['TG_USERNAME']
ACCESS_HASH = int(os.environ.get('TG_ACCESS_HASH', '0'))


class InteruptActions(Exception):
    """!Exception which used to break running actions"""


class SuspiciousUsers():
    """!Class which contains list of suspicious users and methods to work with this list"""
    def __init__(self, telegramapp):
        self.app = telegramapp
        self.users = []

    def joined(self, user_id):
        """!Adding just logged in users in the list of suspicious users if its not in list yet
        @param user_id ID of user which have to be added in the list"""
        if user_id not in self.users:
            self.users.append(user_id)

    def in_list(self, user_id):
        """!Checks if user in the list
        @param user_id ID of user which have to checked if its in list
        @return True is user is in the list"""
        return user_id in self.users

    def remove(self, user_id):
        """!If user is in the list will remove user from it
        @param user_id ID of user which have to be removed from list"""
        if user_id in self.users:
            self.users.remove(user_id)


class Action():
    """!Base class for all of actions which have to be applied to every received message"""
    rank = 0

    def __init__(self, telegramapp):
        self.app = telegramapp

    def log(self, *args, **kwargs):
        """!Log message using main app class log method"""
        self.app.log(*args, **kwargs)

    def matching(self, group, message):
        """!Checks if message should be proccessed by current class object
        @param group Group where message was received
        @param message Message recived in group"""
        for item in filter(lambda i: i.startswith('is') and callable(getattr(self, i)), dir(self)):
            if getattr(self, item)(group, message):
                return True

    async def action(self, group, message):
        """!Hook which appies actions as a reaction on message
        @param group Group where message was received
        @param message Message recived in group"""
        pass

    async def process(self, group, message):
        """!Checks if action should be applied and apply action
        @param group Group where message was received
        @param message Message recived in group"""
        if self.matching(group, message):
            await self.action(group, message)


class KickingAction(Action):
    """!Class which helps to send to banbot potentially bad users"""
    rank = 1

    def is_too_long_named(self, group, message):
        """!Checks if full name of just joined user is longer then 150
        @param group Group where message was received
        @param message Message recived in group
        @return True if if full name of just joined user is longer then 150"""
        if isinstance(message.action, MessageActionChatAddUser):
            if len(message.sender.first_name or []) + len(message.sender.last_name or []) > 150:
                return True

    def is_just_joined(self, group, message):
        """!Used to add every newly joined users into suspicious users list
        @param group Group where message was received
        @param message Message recived in group"""
        if isinstance(message.action, MessageActionChatAddUser):
            self.app.suspicious_users.joined(message.sender.id)

    def is_spammer(self, group, message):
        """!Checks if user is potential spammer if he recently joined and first his message been forwarded
        @param group Group where message was received
        @param message Message recived in group
        @return True user is a potential spammer"""
        if hasattr(message, 'fwd_from') and message.fwd_from is not None:
            if self.app.suspicious_users.in_list(message.sender.id):
                return True

    def is_normal_message(self, group, message):
        """!If message not forwarded and not a user join message remove user from suspicious users list
        @param group Group where message was received
        @param message Message recived in group"""
        if hasattr(message, 'fwd_from') and message.fwd_from is not None:
            return
        if isinstance(message.action, MessageActionChatAddUser):
            return
        self.app.suspicious_users.remove(message.sender.id)

    async def action(self, group, message):
        """!Kick user and remove user id from list of suspicious users
        @param group Group where message was received
        @param message Message recived in group"""
        self.log('kickin %s' % message.sender.first_name)
        await self.app.client.send_message(group, '@banofbot', reply_to=message.id)
        self.app.suspicious_users.remove(message.sender.id)
        raise InteruptActions


class GreetAction(Action):
    """!Class which greets every joined user with a sticker"""
    rank = 2

    async def get_sticker(self):
        """!Finds sticker which have to be used to greet user"""
        iset_id = InputStickerSetID(id=1186758601289498627, access_hash=ACCESS_HASH)
        stick_req = GetStickerSetRequest(stickerset=iset_id)
        return choice([x for x in (await self.app.client(stick_req)).documents])

    def is_just_joined(self, group, message):
        """!Used to add every newly joined users into suspicious users list
        @param group Group where message was received
        @param message Message recived in group"""
        if isinstance(message.action, MessageActionChatAddUser):
            return True

    async def action(self, group, message):
        """!Greet user if he just joined
        @param group Group where message was received
        @param message Message recived in group"""
        sticker = await self.get_sticker()
        self.log("Sending in reply to %s" % message.id)
        await self.app.client.send_file(group, sticker, reply_to=message.id)


class FoodExpertRequiredAction(Action):
    """!Class which claims for food expert if somebody mentioned sensitive topic"""
    rank = 3
    day_limit = 4
    hour_limit = 1

    def __init__(self, *args, **kwargs):
        super(FoodExpertRequiredAction, self).__init__(*args, **kwargs)
        self.hour_mention_timestamps = []
        self.day_mention_timestamps = []

    @property
    def trigger_words(self):
        """!@return List of words it will trigger on"""
        return ['макдак', 'эчпочмак', 'бургер', 'старбакс']

    def update_mention_timestamps(self):
        """!Updates list of hourly and dayly mentions, removes outdated values"""
        beginning_of_hour = int((datetime.now() - timedelta(hours=1)).strftime('%s'))
        beginning_of_day = int((datetime.now() - timedelta(days=1)).strftime('%s'))
        for timestamp in list(self.hour_mention_timestamps):
            if timestamp < beginning_of_hour and timestamp in self.hour_mention_timestamps:
                self.hour_mention_timestamps.remove(timestamp)
        for timestamp in list(self.day_mention_timestamps):
            if timestamp < beginning_of_day and timestamp in self.day_mention_timestamps:
                self.hour_mention_timestamps.remove(timestamp)

    def out_of_limit(self):
        """!Checks if dayly or hourly limit reached
        @return True if any of limit reached"""
        self.update_mention_timestamps()
        if len(self.hour_mention_timestamps) >= self.hour_limit:
            return True
        if len(self.day_mention_timestamps) >= self.day_limit:
            return True

    def word_matched(self, message):
        """!Checks if message test contains sensitive word
        @return True if message contains any of 'trigger_words'"""
        for word in self.trigger_words:
            if message.text and word in message.text.lower():
                return True

    def is_food_expert_required(self, group, message):
        """!@return True if not out of limit and word matched"""
        if not self.out_of_limit() and self.word_matched(message):
            return True

    async def action(self, group, message):
        """!Claims food expert and append timestamp into list of mentions"""
        self.log('Claiming a food expert')
        await self.app.client.send_message(group, '@AliVasilchikova срочно подойдите в чат, требуется ваше экспертное мнение')
        self.hour_mention_timestamps.append(int(datetime.now().strftime('%s')))
        self.day_mention_timestamps.append(int(datetime.now().strftime('%s')))


class TelegramApp():
    """!Main app class which processing new messages and applies actions to it"""
    def __init__(self):
        self.client = None
        self.actions = []
        self.suspicious_users = SuspiciousUsers(self)
        self.load_actions()

    async def connect(self):
        """!Connects to telegram"""
        self.client = TelegramClient(USERNAME, API_ID, API_HASH)
        await self.client.start()
        await self.client.connect()
        if not await self.client.is_user_authorized():
            await self.client.send_code_request(PHONE)
            await self.client.sign_in(PHONE, input('Enter the code: '))

    def load_actions(self):
        """!Finds all subclasses of Action class, initializes it and adds it to the list of actions"""
        for AClass in sorted([x for x in Action.__subclasses__()], key=attrgetter('rank')):
            self.actions.append(AClass(self))

    async def get_dialog_by_name(self, name):
        """!Get all dialogs of current user and finds requested dialog by name
        @param name Title of dialog to find by
        @return dialog object if name matched"""
        for dialog in await self.client.get_dialogs():
            if dialog.name == name:
                return dialog
        raise Exception("dialog not found")

    def log(self, message):
        """!Logs events with timestamp to STDOUT
        @param message Text of message which should be into log"""
        print("%s %s" % (datetime.now().isoformat(), message))
        sys.stdout.flush()

    async def get_messages(self, group, **kwargs):
        """!Gets messages list
        @param group Group object which will be to take messages from
        @return list of messages"""
        messages = sorted([x for x in await self.client.get_messages(group, **kwargs)], key=attrgetter('id'))
        return messages

    def get_last_id(self, messages, last_id=None):
        """!Returns last message id in the list of messages if its not empty
        @param list of messages from which last message id should be taken
        @return ID of last message, but if its empty returns last_id parameter"""
        if not messages:
            return last_id
        else:
            return messages[0].id

    async def apply_actions(self, group, message):
        """!Applies all actions to message
        @param group Group where message was received
        @param message Message recived in group"""
        for action in self.actions:
            try:
                await action.process(group, message)
            except InteruptActions:
                break

    async def stop(self):
        """!Disconnecting from telegram"""
        if self.client is not None:
            self.log('Disconnecting')
            await self.client.disconnect()

    async def run(self):
        """!Gets Belgorod IT dialog starting to monitor every second for new messages and applies all actions to it"""
        await self.connect()
        belgorod_it = await self.get_dialog_by_name('Belgorod IT')
        last_id = self.get_last_id(await self.get_messages(belgorod_it, limit=1))
        while True:
            messages = await self.get_messages(belgorod_it, min_id=last_id, limit=100)
            for message in messages:
                if message.id != last_id:
                    await self.apply_actions(belgorod_it, message)
            last_id = self.get_last_id(messages, last_id=last_id)
            sleep(1)

while True:
    app = None
    app = TelegramApp()
    app.log("Starting script")
    try:
        ioloop = asyncio.get_event_loop()
        ioloop.run_until_complete(app.run())
    except Exception:
        app.log(traceback.format_exc())
        sleep(10)
        app.log("Restarting script")
    finally:
        if app:
            ioloop.run_until_complete(app.stop())
