import discord
from discord import app_commands
from discord.utils import get
from help_queue import HelpQueue
from ui.views.queue_view import QueueView
from ui.views.ta_view import TAView
from ui.helpers.constants import TA_CHANNEL_NAME
from records import QueueEntry
from datetime import datetime
from db import daily_reset, auto_queue_scheduler

import os
from dotenv import load_dotenv

load_dotenv(".env")

intents = discord.Intents.default()
intents.message_content = True

class Bot(discord.Client):
    def __init__(self):
        super().__init__(intents=intents)
        self.tree = app_commands.CommandTree(self)
        self.queue: HelpQueue = HelpQueue()
        self.queue_status_message_id: int | None = None

    async def setup_hook(self):
        # guild = self.get_guild(1503856452027023451)
        # print(guild.name)
        # self.tree.copy_global_to(guild=guild)
        self.add_view(QueueView())
        self.add_view(TAView())
        daily_reset.start()
        auto_queue_scheduler.start(self)
        
        await self.tree.sync()

    async def on_ready(self):
        await self.update_queue_status_message()

    async def get_ta_channel(self) -> discord.TextChannel | None:
        for guild in self.guilds:
            return get(guild.text_channels, name=TA_CHANNEL_NAME)
        return None

    async def build_queue_status(self) -> str:
        status = "OPEN" if self.queue.is_open else "CLOSED"
        queue_text = await self.queue.view()
        return f"**Help Queue Status: {status}**\n{queue_text}"

    async def fetch_or_create_queue_status_message(self) -> discord.Message | None:
        ta_channel = await self.get_ta_channel()
        if ta_channel is None:
            return None

        if self.queue_status_message_id is not None:
            try:
                return await ta_channel.fetch_message(self.queue_status_message_id)
            except discord.NotFound:
                self.queue_status_message_id = None

        async for message in ta_channel.history(limit=50):
            if message.author == self.user and message.content.startswith("**Help Queue Status:"):
                self.queue_status_message_id = message.id
                return message

        status_message = await ta_channel.send(await self.build_queue_status())
        self.queue_status_message_id = status_message.id
        return status_message

    async def update_queue_status_message(self) -> None:
        status_message = await self.fetch_or_create_queue_status_message()
        if status_message is None:
            return

        await status_message.edit(content=await self.build_queue_status())

    async def queue_handler(self, interaction: discord.Interaction, question, is_passoff, in_person, student_name: str):
        entry = QueueEntry(
            user_id=interaction.user.id,
            username=interaction.user.display_name,
            student_name=student_name,
            details=question,
            is_passoff=is_passoff,
            timestamp=datetime.now(),
            in_person=in_person
        )

        await self.queue.add(entry)
        await self.update_queue_status_message()


bot = Bot()

@bot.tree.command(name="queue")
async def queue_panel(interaction: discord.Interaction):
    await interaction.response.send_message(
        "Queue Panel",
        view=QueueView()
    )

@bot.tree.command(name="ta")
async def ta_panel(interaction: discord.Interaction):
    await interaction.response.send_message(
        "TA Panel",
        view=TAView()
    )

token: str = os.getenv("TOKEN")
bot.run(token)