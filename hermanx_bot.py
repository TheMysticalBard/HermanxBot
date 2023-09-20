import os
import re
import discord
import logging
import json
from discord import app_commands
from datetime import datetime
from typing import cast
from discord.interactions import Interaction

from discord.utils import MISSING
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

class ThreadMap:
    def __init__(
            self,
            thread: discord.Thread,
            replies: list[dict]):
        self.replies = replies
        self.thread = thread
    replies: list[dict]
    thread: discord.Thread

class HermanxClient(discord.Client):
    def __init__(
            self,
            *args,
            intents: discord.Intents,
            **options):
        super().__init__(intents=intents, options=options)
        self.tree = app_commands.CommandTree(self)

    async def setup_hook(self):
        self.tree.copy_global_to(guild=TEST_GUILD)
        await self.tree.sync(guild=TEST_GUILD)

async def slack_import(interaction: discord.Interaction, category_name: str):
    global USERS, CHANNELS
    await interaction.response.send_message("Importing started. A ping will be sent to you when importing is completed.", ephemeral=True)
    REASON_STR = f"Imported from Slack export by {interaction.user}"
    import_category = await interaction.guild.create_category(category_name, reason=REASON_STR)

    threads: dict[str, ThreadMap] = {}

    for channel in CHANNELS:
        text_channel = await import_category.create_text_channel(channel["name"], topic=channel["purpose"]["value"], reason=REASON_STR)
        channel_dir = f"./export/{channel['name']}/"
        day_file_names = [f for f in os.listdir(channel_dir) if f.endswith('.json')]
        for day_file_name in sorted(day_file_names, key=file_to_datetime):
            await text_channel.send(f"_ _\n## <t:{int(file_to_datetime(day_file_name).timestamp())}:D>", silent=True)
            with open(f"{channel_dir}/{day_file_name}") as day_file_json:
                FILE = json.load(day_file_json)
            previous_msg_timestamp = None
            for message in FILE:
                if message["type"] != "message":
                    break

                user = USERS[message['user']]
                user_str = f"{user['real_name']} ({user['name']})"
                user_color = discord.Colour.from_str(f"#{user['color']}")
                ts = datetime.fromtimestamp(float(message['ts']))

                extra_space = ""
                if previous_msg_timestamp is not None and (ts - previous_msg_timestamp).total_seconds() > 60 * 60 * 2:
                    extra_space = "_ _"

                previous_msg_timestamp = ts

                if "blocks" in message:
                    message_str = blocks_to_message(message["blocks"])
                elif "subtype" in message and message["subtype"] == "channel_join":
                    user_pattern = re.compile("(?:<@)(U[0-9A-Z]+)(?:>)")
                    user_match = re.search(user_pattern, message['text'])
                    if user_match:
                        message_str = f"@{user_pattern.sub(USERS[user_match.group(1)]['name'], message['text'])}"
                    else:
                        message_str = message['text']
                else:
                    message_str = message['text']
                message_embed = discord.Embed(
                    color=user_color,
                    type="rich",
                    title=user_str,
                    description=message_str,
                    timestamp=ts)

                first_image = True
                if "files" in message:
                    files: list[dict] = message["files"]
                    for file in files:
                        if first_image:
                            first_image = False
                        else:
                            # Send previous image embed, create new embed
                            await text_channel.send(content=extra_space, embed=message_embed, silent=True)
                            extra_space = ""
                            message_embed = discord.Embed(
                                color = user_color,
                                type="rich")

                        if "filetype" in file:
                            match file["filetype"]:
                                case "png" | "jpg" | "gif":
                                    pass
                                case _:
                                    message_embed.add_field(name="", value=file["url_private"])

                        match file["mode"]:
                            case "tombstone":
                                message_embed.add_field(name=":heavy_multiplication_x: This file was deleted.", value="")
                            case "hosted" | "external":
                                message_embed.set_image(url=slack_file_to_image(file))
                            case _ as mode:
                                logging.error(f"Unknown file mode: {mode}")
                                message_embed.set_image(url=slack_file_to_image(file))
                
                if "attachments" in message:
                    attachments = message["attachments"]
                    for attachment in attachments:
                        if first_image:
                            first_image = False
                        else:
                            # Send previous image embed, create new embed
                            await text_channel.send(content=extra_space, embed=message_embed, silent=True)
                            extra_space = ""
                            message_embed = discord.Embed(
                                color = user_color,
                                type="rich")

                        if "thumb_url" in attachment:
                            message_embed.set_image(url=attachment["thumb_url"])
                        elif "image_url" in attachment:
                            message_embed.set_image(url=attachment["image_url"])
                        else:
                            message_embed.set_image(url=attachment["from_url"])

                reaction_send_location = text_channel

                if "thread_ts" in message and "replies" not in message:
                    try:
                        thread = threads[message["thread_ts"]]
                        sent_message = None
                        for reply in thread.replies:
                            if reply["ts"] == message["ts"]:
                                sent_message = await thread.thread.send(embed=message_embed, silent=True)
                                await text_channel.send(f"> **@{user['name']}** replied in a thread.", silent=True)
                                reaction_send_location = thread.thread

                                thread.replies.pop(thread.replies.index(reply))
                                if len(thread.replies) == 0:
                                    threads.pop(message["thread_ts"])
                                break
                        if sent_message is None:
                            sent_message = await text_channel.send(content=extra_space, embed=message_embed, silent=True)
                    except KeyError:
                        logging.error(f"KeyError in replying to thread (thread_ts: {message['thread_ts']}).")
                        sent_message = await text_channel.send(content=extra_space, embed=message_embed, silent=True)
                else:
                    sent_message = await text_channel.send(content=extra_space, embed=message_embed, silent=True)

                if "replies" in message:
                    thread = await sent_message.create_thread(name="Replies", reason=REASON_STR)
                    threads[message["thread_ts"]] = ThreadMap(thread, message["replies"])

                if "reactions" in message:
                    reaction_embed = discord.Embed(
                        type="rich"
                    )
                    for reaction in message["reactions"]:
                        reaction_embed.add_field(name=f":{reaction['name']}:: {reaction['count']}", value="")

                    await reaction_send_location.send(embed=reaction_embed, silent=True)
            break # DEV
        # break # DEV

    await interaction.channel.send(f"{interaction.user.mention}, importing completed.")

class UserPortButton(discord.ui.UserSelect['UserPortView']):
    def __init__(self, placeholder: str, index: int):
        self.index = index
        super().__init__(placeholder=placeholder, min_values=0, row=int(index + 1 / UserPortView.USERS_PER_VIEW))

    async def callback(self, interaction: Interaction):
        self.view.users[self.index]["discord"] = interaction.data

class UserPortView(discord.ui.View):
    USERS_PER_VIEW = 5
    async def select_callback(interaction: discord.Interaction):
        pass

    def __init__(self, users, depth=1):
        self.users = users
        self.depth = depth
        for i in self.USERS_PER_VIEW:
            index = i + self.USERS_PER_VIEW * self.depth
            try:
                select = discord.ui.UserSelect(placeholder=users[index]["name"], min_values=0, row=i)
                select.callback = self.select_callback
                self.add_item(discord.ui.UserSelect)
            except KeyError:
                pass
        super().__init__(title=f"Port Slack Users ({depth}/{len(users)/self.USERS_PER_VIEW})")

class SettingsView(discord.ui.View):
    def __init__(self, category_name: str):
        self.category_name = category_name
        super().__init__()

    select_options=[
        discord.SelectOption(label="Keep Slack mentions as non-functional text", value="False"),
        discord.SelectOption(label="Convert Slack mentions to silent Discord mentions", value="True")
    ]

    @discord.ui.select(cls=discord.ui.Select, options=select_options)
    async def on_submit(self, interaction: discord.Interaction, select: discord.ui.Select):
        global USERS
        port_mentions = select.values[0] == "True"
        if port_mentions:
            user_list = []
            for user_id in USERS.keys():
                user = USERS[user_id]
                user_list.append({ 'id': user_id, 'name': user["name"], 'discord': None })
            # await interaction.response.send_modal(modal=UserPortView(user_list))
            self.remove_item(select)
            await interaction.response.edit_message(content=f"First user: {user_list[0]}", view=None)
        else:
            await slack_import(interaction, self.category_name)

intents = discord.Intents.default()
intents.message_content = True
intents.members = True

client = HermanxClient(intents=intents)

def file_to_datetime(filename: str):
    (year, month, day) = filename.removesuffix(".json").split("-")
    return datetime(year=int(year), month=int(month), day=int(day))

def slack_file_to_image(file: dict):
    match file["filetype"]:
        case "gif":
            expression = re.compile("thumb_([0-9]+)_gif")
            size = None
            for key in file.keys():
                re_match = re.fullmatch(expression, key)
                if re_match:
                    new_size = int(re_match.group(1))
                    if size is None or new_size > size:
                        size = new_size
            return file[f"thumb_{size}_gif"] if size is not None else file["url_private"]
        case "pdf":
            return file["thumb_pdf"]
        case "mp4":
            return file["thumb_video"]
        case "jpg" | "png" | "gdoc":
            expression = re.compile("image_([0-9]+)")
            size = None
            for key in file.keys():
                re_match = re.fullmatch(expression, key)
                if re_match:
                    new_size = int(re_match.group(1))
                    if size is None or new_size > size:
                        size = new_size
            return file[f"thumb_{size}"] if size is not None else file["url_private"]
        case _:
            return file["url_private"]

def decorate(text: str, style: RichTextStyle | None):
    if style is None:
        return text
    style = RichTextStyle(style)
    if style.code:
        if text.count('\n') > 0:
            return f"```{text}```"
        else:
            return f"``{text}``"

    style_text = text.strip()
    if style.bold:
        style_text = f"**{style_text}**"
    if style.italic:
        style_text = f"_{style_text}_"
    if style.strike:
        style_text = f"~~{style_text}~~"
    return style_text.join(text.split(style_text))

def recurse_section(section: RichTextSection):
    text = ""
    for element in section.elements:
        element = RichTextElement(element)
        element_text = None
        
        if element.type == "text":
            element = cast(RichTextText, element)
            element_text = element.text
        
        elif element.type == "emoji":
            element = cast(RichTextEmoji, element)
            if element.unicode is not None:
                element_text = ""
                for char in element.unicode.split("-"):
                    element_text += f"{chr(int(char, 16))}"
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
            element = RichTextLink(element.__dict__)
            if element.text is not None:
                element_text = f"[{element.text}]({element.url})"
            else:
                element_text = element.url
        
        elif element.type == "team":
            element = cast(RichTextTeam, element)
            element_text = f"**@{element.team_id}**"
        
        elif element.type == "user":
            element = cast(RichTextUser, element)
            element_text = f"**@{USERS[element.user_id]['name']}**"
        
        elif element.type == "usergroup":
            element = cast(RichTextUsergroup, element)
            element_text = f"**@{element.usergroup_id}**"
        
        if element_text is not None:
            text += decorate(element_text, element.style)
        else:
            logging.error(f"Unknown rich text element type: {element.type}")
    return text

def blocks_to_message(blocks: list[dict]):
    message_str = ""
    for block in blocks:
        block = Block(block)
        if block.type == "rich_text":
            block = cast(RichTextBlock, block)
            for section in block.elements:
                section = Block(section)
                if section.type == "rich_text_section":
                    section = cast(RichTextSection, section)
                    message_str += recurse_section(section)
                elif section.type == "rich_text_list":
                    section = cast(RichTextList, section)
                    for subsection in section.elements:
                        subsection = RichTextSection(subsection)
                        message_str += recurse_section(subsection)
                else:
                    logging.error(f"Unknown rich text section: {section.type}")
        else:
            logging.error(f"Unknown block type: {block.type}")
            logging.debug(block)
    return message_str

@client.tree.command(name="import", description="Starts importing slack export into a new category.")
@app_commands.describe(
    category_name="The name of the new category"
)
async def _import(interaction: discord.Interaction, category_name: str = "import"):
    await interaction.response.send_message("Import Settings:", view=SettingsView(category_name), ephemeral=True)

@client.tree.command(name="delete-categories", description="Deletes categories matching parameter, including channels inside.")
@app_commands.describe(
    category="The name of the category to delete",
    limit="The number of categories to delete (-1 for all)"
)
async def delete_categories(interaction: discord.Interaction, category: str, limit: int = -1):
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
        if limit == 0:
            break
        if cat.name == category:
            limit -= 1
            num_channels += len(cat.channels)
            for channel in cat.channels:
                await channel.delete(reason=REASON_STR)
            await cat.delete(reason=REASON_STR)
    
    await interaction.followup.send(f"{interaction.user.mention}, categories named {category} and a total of {num_channels} channels deleted.", ephemeral=True)

@client.event
async def on_ready():
    print(f"HermanxBot logged in as {client.user} [{client.user.id}]")

client.run(PRIVATE["discord_key"], log_handler=handler, log_level=log_level)