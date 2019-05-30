from datetime import timedelta, datetime
from random import choice

from telethon.tl.functions.messages import GetStickerSetRequest
from telethon.tl.types import MessageActionChatAddUser, InputStickerSetID


class InteruptActions(Exception):
    """!Exception which used to break running actions"""


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

    def pre_action(self, group, message):
        """!Hook which runs if matched before action hook
        @param group Group where message was received
        @param message Message recived in group"""
        pass

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
            self.pre_action(group, message)
            await self.action(group, message)


class CountLimitedAction(Action):
    rank = 0
    day_limit = 0
    hour_limit = 0

    def __init__(self, *args, **kwargs):
        super(CountLimitedAction, self).__init__(*args, **kwargs)
        self.hour_limit_timestamps = []
        self.day_limit_timestamps = []

    def pre_action(self, group, message):
        """!Adds timestamp to day or hour list to monitor limits
        @param group Group where message was received
        @param message Message recived in group"""
        self.hour_limit_timestamps.append(int(datetime.now().strftime('%s')))
        self.day_limit_timestamps.append(int(datetime.now().strftime('%s')))

    def update_limit_timestamps(self):
        """!Updates list of hourly and dayly mentions, removes outdated values"""
        beginning_of_hour = int((datetime.now() - timedelta(hours=1)).strftime('%s'))
        beginning_of_day = int((datetime.now() - timedelta(days=1)).strftime('%s'))
        for timestamp in list(self.hour_limit_timestamps):
            if timestamp < beginning_of_hour and timestamp in self.hour_limit_timestamps:
                self.hour_limit_timestamps.remove(timestamp)
        for timestamp in list(self.day_limit_timestamps):
            if timestamp < beginning_of_day and timestamp in self.day_limit_timestamps:
                self.hour_limit_timestamps.remove(timestamp)

    def out_of_limit(self):
        """!Checks if dayly or hourly limit reached
        @return True if any of limit reached"""
        self.update_limit_timestamps()
        if len(self.hour_limit_timestamps) >= self.hour_limit:
            return True
        if len(self.day_limit_timestamps) >= self.day_limit:
            return True


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


class FoodExpertRequiredAction(CountLimitedAction):
    """!Class which claims for food expert if somebody mentioned sensitive topic"""
    rank = 3
    day_limit = 4
    hour_limit = 1

    @property
    def trigger_words(self):
        """!@return List of words it will trigger on"""
        return ['макдак', 'эчпочмак', 'бургер', 'старбакс']

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
        await self.app.client.send_message(group, '@AliVasilchikova срочно подойдите в чат, требуется ваше экспертное мнение', reply_to=message.id)


class PlusAction(CountLimitedAction):
    """!Class which aggrees with author of message contained + signs only and increases level of it"""
    rank = 4
    day_limit = 4
    hour_limit = 1

    def word_matched(self, message):
        """!Checks if message contains of + only
        @return True if message contains + signs only"""
        if message.text and not message.text.strip('+'):
            return True

    def is_plus_required(self, group, message):
        """!@return True if not out of limit and plus message required"""
        if not self.out_of_limit() and self.word_matched(message):
            return True

    async def action(self, group, message):
        """!Sends pluses plus plus message"""
        self.log('Send plus plus plus message')
        await self.app.client.send_message(group, message.text + "+", reply_to=message.id)
