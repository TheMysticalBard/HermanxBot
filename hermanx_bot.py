import discord
import json

with open("./private.json") as private:
    PRIVATE = json.load(private)

intents = discord.Intents.default()
intents.message_content = True

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

client.run(PRIVATE["discord_key"])