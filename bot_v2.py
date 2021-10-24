import discord
import asyncio
import requests
import os
import git
import json
import sys
import youtube_dl
from youtube_search import YoutubeSearch

import urllib.parse, urllib.request, re
# import requests
from dotenv import load_dotenv

from discord.ext import commands
from discord import Embed, FFmpegPCMAudio
from discord.utils import get

'''

INSTALLING YOUTUBE-DL

pip install -U git+https://github.com/l1ving/youtube-dl

'''

load_dotenv()

DISCORD_TOKEN = os.getenv("discord_token")
# QUEUE = []

youtube_dl.utils.bug_reports_message = lambda: ''

ytdl_format_options = {
    'format': 'bestaudio/best',
    'outtmpl': './songs/%(extractor)s-%(id)s-%(title)s.%(ext)s',
    'restrictfilenames': True,
    'noplaylist': True,
    'nocheckcertificate': True,
    'ignoreerrors': False,
    'logtostderr': False,
    'quiet': True,
    'no_warnings': True,
    'default_search': 'auto',
    'source_address': '0.0.0.0'
}

ffmpeg_options = {
    'options': '-vn'
}

ytdl = youtube_dl.YoutubeDL(ytdl_format_options)

class YTDLSource(discord.PCMVolumeTransformer):
    def __init__(self, source, *, data, volume=0.5):
        super().__init__(source, volume)

        self.data = data

        self.title = data.get('title')
        self.url = data.get('url') 
    
    @classmethod
    async def from_url(cls, url, *, loop=None):
        """Prepare the song from given search or url"""
        if loop is None:
            loop = asyncio.get_event_loop()
        data = ytdl.extract_info(url, download=False)
        
        data = data["entries"][0]

        filename = data["url"] 
        return cls(discord.FFmpegPCMAudio(filename, **ffmpeg_options), data=data)
            

class Music(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.queue = []
        self.paused = False
    
    @commands.command(name="search")
    async def search(self, ctx, *, url):
        async with ctx.typing():
            if url[:3] == "http":
                await ctx.send("Cannot search with a link!")
                return
            
            # Get the top 10 results
            results = YoutubeSearch(url, max_results=10).to_dict()
            titles = [result["title"] for result in results]
        
        await ctx.send('\n'.join(["```"] + [f"{i+1}\t{title}" for i, title in enumerate(titles)] + ["\n```"]))
        
        def check(m):
            # Check if message is valid
            try:
                m_num = int(m.content) - 1
            except ValueError:
                return False
            
            if 0 <= m_num <= 9 and m.author == ctx.author:
                # Valid selection
                return True
            else:
                # Invalid selection
                return False
        
        try:
            msg = await self.bot.wait_for("message", check=check, timeout=10.0)
        except asyncio.TimeoutError:
            await ctx.send("Search canceled! Please search again...")
            return

        # Valid selection
        player = await self.get_song(ctx, titles[int(msg.content) - 1])
        await self.add_queue(ctx, player)
        await self.start_playing(ctx)
             
    @commands.command(name="join")
    async def join(self, ctx):
        """Join a discord voice channel"""
        if not ctx.message.author.voice:
            await ctx.send("You are not connected to a voice channel!")
            return
        else:
            channel = ctx.message.author.voice.channel
            await ctx.send(f'Connected to ``{channel}``')
            await ctx.send(__version__())

        await channel.connect()

    @commands.command(name="play", aliases=["p"])
    async def play(self, ctx, *, url):
        """Play a song on with the given url/search terms"""
        try:
            player = await self.get_song(ctx, url)
            await self.add_queue(ctx, player)
            await self.start_playing(ctx)
        except Exception as e:
            print(e)
            await ctx.send("Somenthing went wrong - please try again later!")

    async def play_internal(self, ctx, url):
        """Play a song on with the given url/search terms"""
        try:
            player = await self.get_song(ctx, url)
            await self.add_queue(ctx, player)
            await self.start_playing(ctx)
        except Exception as e:
            print(e)
            await ctx.send("Somenthing went wrong - please try again later!")

    @commands.command(name="playtop", aliases=["pt"])
    async def play_top(self, ctx, *, url):
        player = await self.get_song(ctx, url)
        await self.add_queue(ctx, player, position=0)
        await self.start_playing(ctx)
    
    @commands.command(name="pause")
    async def pause(self, ctx):
        """Pause the bot"""
        voice = get(self.bot.voice_clients, guild=ctx.guild)

        voice.pause()
        self.paused = True

        user = ctx.message.author.mention
        await ctx.send(f"Bot was paused by {user}")

    @commands.command(name="resume")
    async def resume(self, ctx):
        """Resume the bot"""
        voice = get(self.bot.voice_clients, guild=ctx.guild)

        voice.resume()
        self.paused = False

        user = ctx.message.author.mention
        await ctx.send(f"Bot was resumed by {user}")

    @commands.command(name="remove", aliases=["r"])
    async def remove(self, ctx, number):
        """Remove a song from the queue"""
        try:
            del self.queue[int(number) - 1]
            if len(self.queue) < 1:
                await ctx.send("Your queue is empty now!")
            else:
                await ctx.send(f'Your queue is now {self.view_queue(ctx)}')
        except:
            await ctx.send("Remove Failed! Number is out of bounds...")

    @commands.command(name="clear", aliases=["c"])
    async def clear(self, ctx):
        """Clear the entire queue"""
        self.queue.clear()
        user = ctx.message.author.mention
        await ctx.send(f"The queue was cleared by {user}")

    @commands.command(name="queue", aliases=["q"])
    async def view_queue(self, ctx):
        """Print out the queue to the text channel"""
        if len(self.queue) < 1:
            await ctx.send("The queue is empty - nothing to see here!")
        else:   
            await ctx.send('\n'.join(["```"] + [f"{i+1}\t" + song.title for i, song in enumerate(self.queue)] + ["\n```"]))       

    @commands.command()
    async def leave(self, ctx):
        """Disconnects the bot from the voice channel"""
        voice_client = ctx.message.guild.voice_client
        user = ctx.message.author.mention
        await voice_client.disconnect()
        await ctx.send(f'Disconnected by {user}')

    @commands.command()
    async def skip(self, ctx):
        voice = get(self.bot.voice_clients, guild=ctx.guild)
        voice.stop()
        await self.start_playing(ctx)
        
    async def get_song(self, ctx, url):
        """Get the player for given search query"""
        async with ctx.typing():
            if url[:3] != "http":
                # User is searching via words
                url = "ytsearch1: " + url
            player = await YTDLSource.from_url(url, loop=self.bot.loop)
        return player
    
    async def add_queue(self, ctx, player, position=-1):
        """Add a song to the queue at given position"""
        try:
            if position == -1:
                self.queue.append(player)
            else:
                self.queue.insert(position, player)
                
            user = ctx.message.author.mention
            await ctx.send(f'``{player.title}`` was added to the queue by {user}!')
        except:
            await ctx.send(f"Couldnt add {player.title} to the queue!")
    
    async def start_playing(self, ctx):
        """Start playing the queue"""
        voice_client = ctx.message.guild.voice_client
        while len(self.queue) > 0:
            if not voice_client.is_playing() and not self.paused:
                # Bot currently playing a song
                player = self.queue.pop(0)
                await ctx.send("Now playing a song!")
                voice_client.play(player)
            await asyncio.sleep(1)
    
    @play.before_invoke
    @search.before_invoke
    async def ensure_voice(self, ctx):
        """Make sure the bot connected to a voice channel"""
        if ctx.voice_client is None:
            if ctx.author.voice:
                await ctx.author.voice.channel.connect()
            else:
                await ctx.send("You are not connected to a voice channel.")
                raise commands.CommandError("Author not connected to a voice channel.")
            
    @commands.command(name="got")
    async def got(self, ctx):
        await self.play(ctx, "http://www.youtube.com/watch?v=OQWGQBFIOg0")
    
    @commands.command(name="gottem")
    async def talk(self, ctx):
        f = open("gottext.txt","r")
        y = f.read()
        got10 = ""
        gotcount = 10
        for x in range(0,len(y)):
            got10 += y[x]
            gotcount += 1
            if gotcount == 200:
                await ctx.send(got10)
                got10 = ""
                gotcount = 0

    @commands.command(name="playlist")
    async def playlist(self, ctx, url):
        try:
            playlist_id = url.split("list=")[1]
            requests_url = "https://www.googleapis.com/youtube/v3/playlistItems?part=snippet&maxResults=50&playlistId=" + playlist_id + "&key=AIzaSyDg97zNz31Z_6ztxKVCmy_kMfzta5jNsHA"
            r = requests.get(requests_url)
            json_file = json.loads(r.text)
            for item in json_file['items']:
                await ctx.send("adding " + len(json_file['items']) +" items to queue")
                await self.play_internal(ctx, item['snippet']['resourceId']['videoId'])
                #await ctx.send(item['snippet']['resourceId']['videoId'])


        except Exception as e:
            await ctx.send(e)
            await ctx.send(requests_url)


                
    @commands.command(name="update")
    async def update(self, ctx):
        direct = os.getcwd()
        os.chdir(direct)
        await ctx.send("begining update - use .join to rejoin")
        os.system("python3 updater.py")
       
        await reboot(direct)
        #help
        

def setup(client):
    client.add_cog(Music(client))

def reboot(direct):
    args = sys.argv[:]
    args.insert(0, sys.executable)
    os.chdir(direct)
    os.execv(sys.executable, args)
    exit()

def __version__():
    return "Version 1.2d"

    
if __name__ == '__main__':
    bot = commands.Bot(command_prefix='.')
    setup(bot)
    bot.run(DISCORD_TOKEN)
