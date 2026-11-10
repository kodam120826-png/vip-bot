import json
import random
import datetime
from zoneinfo import ZoneInfo
import discord
from discord.ext import commands, tasks

intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix="!", intents=intents)

# 💡 [중요] 아래 채널 ID와 봇 토큰을 본인 것으로 꼭 바꿔주세요!
CHANNEL_ID = 1566416489270087843  # 노래를 받을 디스코드 채널 ID
BOT_TOKEN = os.environ.get("BOT_TOKEN")
def load_songs():
    with open("songs.json", "r", encoding="utf-8") as f:
        return json.load(f)

def load_history():
    try:
        with open("history.json", "r", encoding="utf-8") as f:
            return json.load(f)
    except FileNotFoundError:
        return []

def save_history(history):
    with open("history.json", "w", encoding="utf-8") as f:
        json.dump(history, f, ensure_ascii=False, indent=4)

@bot.event
async def on_ready():
    print(f"로그인 완료: {bot.user.name}")
    daily_bigbang_song.start()

@tasks.loop(time=datetime.time(hour=9, minute=0, tzinfo=ZoneInfo("Asia/Seoul")))
async def daily_bigbang_song():
    channel = bot.get_channel(CHANNEL_ID)
    if channel is not None:
        songs = load_songs()
        history = load_history()
        
        available_songs = [s for s in songs if s['title'] not in history]
        
        if not available_songs:
            history = []
            available_songs = songs
            await channel.send("🔄 모든 빅뱅 노래가 한 바퀴 돌았습니다! 기록을 초기화하고 다시 시작합니다. 🎶")
        
        song = random.choice(available_songs)
        history.append(song['title'])
        save_history(history)
        
        embed = discord.Embed(
            title="🎶 오늘의 빅뱅 추천곡!",
            description=f"오늘 추천해 드릴 곡은 **{song['title']}** 입니다!",
            color=0xFFD700
        )
        embed.add_field(name="YouTube 링크", value=song['url'], inline=False)
        await channel.send(embed=embed)

@daily_bigbang_song.before_loop
async def before_daily_song():
    await bot.wait_until_ready()

@bot.command(name="빅뱅추천")
async def recommend_song(ctx):
    songs = load_songs()
    history = load_history()
    available_songs = [s for s in songs if s['title'] not in history]
    
    if not available_songs:
        history = []
        available_songs = songs
        await ctx.send("🔄 모든 곡이 소진되어 기록이 초기화되었습니다!")
        
    song = random.choice(available_songs)
    history.append(song['title'])
    save_history(history)
    
    embed = discord.Embed(
        title="🎧 [수동 요청] 오늘의 빅뱅 추천곡",
        description=f"**{song['title']}**",
        color=0xFFD700
    )
    embed.add_field(name="YouTube 링크", value=song['url'], inline=False)
    await ctx.send(embed=embed)

bot.run(BOT_TOKEN)
