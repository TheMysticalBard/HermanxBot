import discord
import logging
import json

log_level = logging.INFO
handler = logging.FileHandler(filename="discord.log", encoding="utf-8", mode="w")

with open("./private.json") as private:
    PRIVATE = json.load(private)

intents = discord.Intents.default()
intents.message_content = True
intents.members = True
client = discord.Client(intents=intents)

@client.event
async def on_ready():
    print(f"HermanxBot logged in as {client.user}")

@client.event
async def on_message(message: discord.Message):
    if message.author == client.user:
        return
    
    if message.content.startswith('ping'):
        await message.channel.send("pong")

client.run(PRIVATE["discord_key"], log_handler=handler, log_level=log_level)