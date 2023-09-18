import os
import discord
import logging
import json
from discord import app_commands
from datetime import datetime
from typing import cast
from slack_types import *

log_level = logging.INFO
handler = logging.FileHandler(filename="discord.log", encoding="utf-8", mode="w")

with open("./private.json") as private:
    PRIVATE = json.load(private)

with open("./export/channels.json") as channels_json:
    CHANNELS: list = json.load(channels_json)

with open("./export/users.json") as users_json:
    USERS: list = json.load(users_json)

USERS = {user["id"]: user for user in USERS}


TEST_GUILD = discord.Object(id=PRIVATE["test_guild_id"])

class HermanxClient(discord.Client):
    def __init__(
            self,
            *args,
            intents: discord.Intents,
            **options
            ):
        super().__init__(intents=intents, options=options)
        self.tree = app_commands.CommandTree(self)

    async def setup_hook(self):
        self.tree.copy_global_to(guild=TEST_GUILD)
        await self.tree.sync(guild=TEST_GUILD)

intents = discord.Intents.default()
intents.message_content = True
intents.members = True

client = HermanxClient(intents=intents)

def decorate(text: str, style: RichTextStyle | None):
    if style is None:
        return text
    if style.code:
        if text.count('\n') > 0:
            return f"```{text}```"
        else:
            return f"``{text}``"
    if style.bold:
        text = f"**{text}**"
    if style.italic:
        text = f"_{text}_"
    if style.strike:
        text = f"~~{text}~~"
    return text

def blocks_to_message(blocks: list[dict]):
    message_str = ""
    for block in blocks:
        block = Block(block)
        if block.type == "rich_text":
            block = cast(RichTextBlock, block)
            for section in block.elements:
                section = RichTextSection(section)
                for element in section.elements:
                    element = RichTextElement(element)
                    element_text = None
                    
                    if element.type == "text":
                        element = cast(RichTextText, element)
                        element_text = element.text
                    
                    elif element.type == "emoji":
                        element = cast(RichTextEmoji, element)
                        if element.unicode is not None:
                            element_text = f"\\u{element.unicode}"
                        else:
                            element_text = f":{element.name}:"
                    
                    elif element.type == "broadcast":
                        element = cast(RichTextBroadcast, element)
                        element_text = f"@{element.range}"

                    elif element.type == "channel":
                        element = cast(RichTextChannel, element)
                        channel_id_to_name = {channel["id"]: channel["name"] for channel in CHANNELS}
                        element_text = f"#{channel_id_to_name[element.channel_id]}"
                    
                    elif element.type == "date":
                        element = cast(RichTextDate, element)
                        element_text = f"<t:{int(float(element.timestamp))}:f>"
                    
                    elif element.type == "link":
                        element = cast(RichTextLink, element)
                        if element.text is not None:
                            element_text = f"[{element.text}]({element.url})"
                        else:
                            element_text = element.url
                    
                    elif element.type == "team":
                        element = cast(RichTextTeam, element)
                        element_text = f"@{element.team_id}"
                    
                    elif element.type == "user":
                        element = cast(RichTextUser, element)
                        element_text = f"@{USERS[element.user_id]['name']}"
                    
                    elif element.type == "usergroup":
                        element = cast(RichTextUsergroup, element)
                        element_text = f"@{element.usergroup_id}"
                    
                    if element_text is not None:
                        message_str += decorate(element_text, element.style)
                    else:
                        logging.error(f"Unknown rich text element type: {element.type}")
        else:
            logging.error(f"Unknown block type: {block.type}")
            logging.debug(block)
    return message_str


@client.tree.command(name="import", description="Starts importing slack export into a new category.")
@app_commands.describe(
    category="The name of the new category"
)
async def _import(interaction: discord.Interaction, category: str = "import"):
    global USERS, CHANNELS
    await interaction.response.send_message("Importing started. A ping will be sent to you when importing is completed.", ephemeral=True)
    REASON_STR = f"Imported from Slack export by {interaction.user}"
    import_category = await interaction.guild.create_category(category, reason=REASON_STR)

    for channel in CHANNELS:
        text_channel = await import_category.create_text_channel(channel["name"], topic=channel["purpose"]["value"], reason=REASON_STR)
        channel_dir = f"./export/{channel['name']}/"
        day_file_names = [f for f in os.listdir(channel_dir) if f.endswith('.json')]
        for day_file_name in day_file_names:
            with open(f"{channel_dir}/{day_file_name}") as day_file_json:
                FILE = json.load(day_file_json)
            for message in FILE:
                if message["type"] != "message":
                    break
                
                user = USERS[message['user']]
                user_str = f"{user['name']} ({user['real_name']})"
                ts = datetime.fromtimestamp(float(message['ts']))
                if "blocks" in message:
                    message_str = blocks_to_message(message["blocks"])
                else:
                    message_str = message['text']
                message_embed = discord.Embed(
                    color=discord.Colour.from_str(f"#{user['color']}"),
                    type="rich",
                    timestamp=ts)\
                    .set_author(name=user_str)\
                    .add_field(name='\u200B', value=message_str)
                
                if "files" in message:
                    message_embed.set_image(url=message["files"][0]["url_private"])
                
                if "attachments" in message:
                    message_embed.set_image(url=message["attachments"])

                await text_channel.send(embed=message_embed)
            break # DEV
        break # DEV

    await interaction.followup.send(f"{interaction.user.mention}, importing completed.", ephemeral=True)

@client.tree.command(name="delete-category", description="Deletes the first category matching parameter, including channels inside.")
@app_commands.describe(
    category="The name of the category to delete"
)
async def delete_category(interaction: discord.Interaction, category: str):
    if category == "" or category is None:
        await interaction.response.send_message("Category name must be supplied, quitting.", ephemeral=True)
        return

    category_names = [cat.name for cat in interaction.guild.categories]
    if category not in category_names:
        await interaction.response.send_message("Category not found in guild, quitting.", ephemeral=True)
        return

    await interaction.response.send_message("Delete started. A ping will be sent to you when deletion is complted.", ephemeral=True)
    REASON_STR = f"{interaction.user} ran channel delete command"
    num_channels = 0

    for cat in interaction.guild.categories:
        if cat.name == category:
            cat_found = True
            num_channels = len(cat.channels)
            for channel in cat.channels:
                await channel.delete(reason=REASON_STR)
            await cat.delete(reason=REASON_STR)
            break
    
    await interaction.followup.send(f"{interaction.user.mention}, category {category} with {num_channels} channels deleted.", ephemeral=True)

@client.event
async def on_ready():
    print(f"HermanxBot logged in as {client.user} [{client.user.id}]")

client.run(PRIVATE["discord_key"], log_handler=handler, log_level=log_level)