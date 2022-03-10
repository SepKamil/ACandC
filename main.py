import os
import discord
import d20
import re
client = discord.Client()


@client.event
async def on_message(message):
    if message.author == client.user:
        return
    msg = message.content
    if '/roll' in msg:
        x=re.split("\s",msg)
        y=d20.roll(x[1])
        await message.channel.send(y.result)

client.run(os.getenv('TOKEN'))
