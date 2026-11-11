import os
import json
import random
import datetime
from zoneinfo import ZoneInfo
import discord
from discord.ext import commands, tasks

intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix="!", intents=intents)

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
    
    # 디스코드 서버에 슬래시 명령어 목록 동기화
    try:
        synced = await bot.tree.sync()
        print(f"슬래시 명령어 {len(synced)}개 동기화 완료")
    except Exception as e:
        print(f"동기화 에러: {e}")
        
    if not daily_bigbang_song.is_running():
        daily_bigbang_song.start()

# ----------------- 🎵 빅뱅 팬덤 맞춤 슬래시 명령어 -----------------

# 1. 오늘의 빅뱅 추천곡 수동 호출
@bot.tree.command(name="오늘의추천", description="오늘의 빅뱅 추천곡을 수동으로 뽑습니다!")
async def slash_recommend_song(interaction: discord.Interaction):
    songs = load_songs()
    history = load_history()
    available_songs = [s for s in songs if s['title'] not in history]
    
    if not available_songs:
        history = []
        available_songs = songs
        await interaction.response.send_message("🔄 모든 곡이 소진되어 기록이 초기화되었습니다!", ephemeral=True)
        
    song = random.choice(available_songs)
    history.append(song['title'])
    save_history(history)
    
    embed = discord.Embed(
        title="🎧 오늘의 빅뱅 추천곡 (수동)",
        description=f"오늘 추천해 드릴 곡은 **{song['title']}** 입니다!",
        color=0xFFD700
    )
    embed.add_field(name="YouTube 링크", value=song['url'], inline=False)
    await interaction.response.send_message(embed=embed)

# 2. 빅뱅/지드래곤 레전드 명언 & 명대사 뽑기
@bot.tree.command(name="명언", description="빅뱅 & 지드래곤의 레전드 명언과 명대사를 소환합니다.")
async def slash_quotes(interaction: discord.Interaction):
    quotes = [
        "기적을 믿지 마세요, 노력을 믿으세요.",
        "정신 차려, 이 각박한 세상 속에서.",
        "실패는 성공의 어머니가 아니라, 성공의 하녀일 뿐이다.",
        "내가 만든 길을 걸어갈 뿐이야.",
        "남들의 시선에 갇히지 말고 너만의 색깔로그려."
    ]
    chosen_quote = random.choice(quotes)
    
    embed = discord.Embed(
        title="👑 VIP Lounge 명언 릴레이",
        description=f"✨ *\"{chosen_quote}\"*",
        color=0x111111
    )
    embed.set_footer(text="BIGBANG IS V.I.P")
    await interaction.response.send_message(embed=embed)

# 3. 유저 제재 기록 남기기
@bot.tree.command(name="제재", description="규칙을 위반한 유저에 대한 제재 기록을 남깁니다.")
async def slash_sanction(interaction: discord.Interaction, member: discord.Member, reason: str):
    embed = discord.Embed(
        title="🚨 VIP 서버 제재 조치 안내",
        description="관리자에 의해 제재가 처리되었습니다.",
        color=0xFF0000
    )
    embed.add_field(name="대상 유저", value=member.mention, inline=True)
    embed.add_field(name="제재 사유", value=reason, inline=True)
    embed.set_footer(text=f"처리 관리자: {interaction.user.name}")
    
    await interaction.response.send_message(embed=embed)

# 4. 공지사항 / 원하는 글자 임베드 박스 전송
@bot.tree.command(name="말하기", description="입력한 내용을 깔끔한 임베드 박스로 대신 전송합니다.")
async def slash_say(interaction: discord.Interaction, message: str):
    embed = discord.Embed(
        description=message,
        color=0x00FF00
    )
    embed.set_author(name=interaction.user.display_name, icon_url=interaction.user.display_avatar.url)
    
    await interaction.response.send_message(embed=embed)

# ----------------- ⏰ 매일 자동 실행되는 추천 태스크 -----------------

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

bot.run(BOT_TOKEN)
