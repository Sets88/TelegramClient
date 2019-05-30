import asyncio
import os
import sys
import traceback

from datetime import datetime
from operator import attrgetter
from time import sleep

from telethon import TelegramClient

from actions import InteruptActions, BaseAction


API_ID = os.environ['TG_API_ID']
API_HASH = os.environ['TG_API_HASH']
PHONE = os.environ['TG_PHONE']
USERNAME = os.environ['TG_USERNAME']


class TelegramApp():
    """!Main app class which processing new messages and applies actions to it"""
    def __init__(self):
        self.client = None
        self.actions = []
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
        subclasses = BaseAction.__subclasses__()
        for action in subclasses:
            subclasses.extend(action.__subclasses__())
        for AClass in sorted([x for x in subclasses], key=attrgetter('rank')):
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
