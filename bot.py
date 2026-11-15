import os
import json
import random
import datetime
from zoneinfo import ZoneInfo
from threading import Thread
from flask import Flask
import discord
from discord import app_commands
from discord.ext import commands, tasks

# 1. 렌더 포트 에러 방지용 가벼운 웹 서버 설정 (Flask)
app = Flask('')

@app.route('/')
def home():
    return "VIP Bot is alive and running!"

def run_flask():
    app.run(host='0.0.0.0', port=int(os.environ.get("PORT", 8080)))

def keep_alive():
    t = Thread(target=run_flask)
    t.start()

# ----------------- 디스코드 봇 설정 -----------------

intents = discord.Intents.default()
intents.message_content = True
intents.members = True
bot = commands.Bot(command_prefix="!", intents=intents)

CHANNEL_ID = 1566416489270087843  # 추천곡을 받을 채널 ID
BOT_TOKEN = os.environ.get("BOT_TOKEN")

# 운영진 근태 데이터 저장소
work_records = {}
user_warnings = {}

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

def format_duration(seconds: int) -> str:
    hours, remainder = divmod(seconds, 3600)
    minutes, _ = divmod(remainder, 60)
    if hours > 0:
        return f"{hours}시간 {minutes}분"
    return f"{minutes}분"

@bot.event
async def on_ready():
    print(f"로그인 완료: {bot.user.name}")
    try:
        synced = await bot.tree.sync()
        print(f"슬래시 명령어 {len(synced)}개 동기화 완료")
    except Exception as e:
        print(f"동기화 에러: {e}")
        
    if not daily_bigbang_song.is_running():
        daily_bigbang_song.start()

# ----------------- 💼 1. 운영진 전용 출퇴근 & 자리비움 로그 -----------------

@bot.tree.command(name="출근", description="운영진 출근 기록을 남깁니다. (관리자 전용)")
@app_commands.checks.has_permissions(manage_messages=True)
async def slash_clock_in(interaction: discord.Interaction):
    user_id = interaction.user.id
    now = datetime.datetime.now(ZoneInfo("Asia/Seoul"))
    
    if user_id in work_records:
        prev_time = work_records[user_id]["start"].strftime("%H시 %M분")
        await interaction.response.send_message(
            f"⚠️ **{interaction.user.display_name}**님은 이미 **{prev_time}**에 출근 처리가 되어 있습니다! 먼저 `/퇴근`을 해주세요.",
            ephemeral=True
        )
        return

    work_records[user_id] = {
        "start": now,
        "away_start": None,
        "total_away_seconds": 0
    }
    time_str = now.strftime("%Y-%m-%d %H:%M:%S")
    
    embed = discord.Embed(
        title="🟢 운영진 출근 로그",
        description=f"**{interaction.user.mention}**님이 업무를 시작했습니다.",
        color=0x2ECC71
    )
    embed.add_field(name="출근 시각", value=f"`{time_str}`", inline=False)
    embed.set_thumbnail(url=interaction.user.display_avatar.url)
    embed.set_footer(text="VIP 서버 운영팀 근태 기록")
    await interaction.response.send_message(embed=embed)

@bot.tree.command(name="자리비움", description="근무 중 잠시 자리를 비울 때 기록합니다. (관리자 전용)")
@app_commands.checks.has_permissions(manage_messages=True)
async def slash_away(interaction: discord.Interaction, reason: str = "개인 용무"):
    user_id = interaction.user.id
    now = datetime.datetime.now(ZoneInfo("Asia/Seoul"))
    
    if user_id not in work_records:
        await interaction.response.send_message("❌ 먼저 `/출근`을 한 상태에서만 자리비움을 사용할 수 있습니다.", ephemeral=True)
        return
        
    if work_records[user_id]["away_start"] is not None:
        await interaction.response.send_message("⚠️ 이미 자리비움 상태입니다! 돌아오셨다면 `/복귀`를 눌러주세요.", ephemeral=True)
        return
        
    work_records[user_id]["away_start"] = now
    
    embed = discord.Embed(
        title="🟡 운영진 자리비움 로그",
        description=f"**{interaction.user.mention}**님이 잠시 자리를 비웠습니다.",
        color=0xF1C40F
    )
    embed.add_field(name="자리비움 시각", value=f"`{now.strftime('%H:%M:%S')}`", inline=True)
    embed.add_field(name="사유", value=reason, inline=True)
    embed.set_footer(text="복귀 시 /복귀 명령어를 입력해 주세요.")
    await interaction.response.send_message(embed=embed)

@bot.tree.command(name="복귀", description="자리비움 상태를 해제하고 업무에 복귀합니다. (관리자 전용)")
@app_commands.checks.has_permissions(manage_messages=True)
async def slash_back(interaction: discord.Interaction):
    user_id = interaction.user.id
    now = datetime.datetime.now(ZoneInfo("Asia/Seoul"))
    
    if user_id not in work_records or work_records[user_id]["away_start"] is None:
        await interaction.response.send_message("❌ 현재 자리비움 상태가 아닙니다.", ephemeral=True)
        return
        
    away_start = work_records[user_id]["away_start"]
    away_duration = int((now - away_start).total_seconds())
    work_records[user_id]["total_away_seconds"] += away_duration
    work_records[user_id]["away_start"] = None
    
    embed = discord.Embed(
        title="🔵 운영진 업무 복귀 로그",
        description=f"**{interaction.user.mention}**님이 자리에서 복귀했습니다!",
        color=0x3498DB
    )
    embed.add_field(name="복귀 시각", value=f"`{now.strftime('%H:%M:%S')}`", inline=True)
    embed.add_field(name="이번 자리비움 시간", value=f"**{format_duration(away_duration)}**", inline=True)
    embed.set_footer(text="VIP 서버 운영팀 근태 기록")
    await interaction.response.send_message(embed=embed)

@bot.tree.command(name="퇴근", description="운영진 퇴근 기록과 실제 근무 시간을 남깁니다. (관리자 전용)")
@app_commands.checks.has_permissions(manage_messages=True)
async def slash_clock_out(interaction: discord.Interaction):
    user_id = interaction.user.id
    now = datetime.datetime.now(ZoneInfo("Asia/Seoul"))
    
    if user_id not in work_records:
        await interaction.response.send_message(
            f"❌ **{interaction.user.display_name}**님의 출근 기록이 없습니다! 먼저 `/출근`을 눌러주세요.",
            ephemeral=True
        )
        return

    record = work_records.pop(user_id)
    start_time = record["start"]
    total_away = record["total_away_seconds"]
    
    if record["away_start"] is not None:
        total_away += int((now - record["away_start"]).total_seconds())
        
    total_elapsed = int((now - start_time).total_seconds())
    actual_work = max(0, total_elapsed - total_away)
    
    embed = discord.Embed(
        title="🔴 운영진 퇴근 로그",
        description=f"**{interaction.user.mention}**님이 업무를 종료했습니다. 수고하셨습니다!",
        color=0xE74C3C
    )
    embed.add_field(name="출근 시각", value=f"`{start_time.strftime('%H:%M:%S')}`", inline=True)
    embed.add_field(name="퇴근 시각", value=f"`{now.strftime('%H:%M:%S')}`", inline=True)
    embed.add_field(name="자리비움 합계", value=f"`{format_duration(total_away)}`", inline=True)
    embed.add_field(name="실제 순수 근무 시간", value=f"**{format_duration(actual_work)}**", inline=False)
    embed.set_thumbnail(url=interaction.user.display_avatar.url)
    embed.set_footer(text="VIP 서버 운영팀 근태 기록")
    await interaction.response.send_message(embed=embed)

# ----------------- 🛡️ 2. 서버 관리 필수 기능 (관리자 전용) -----------------

@bot.tree.command(name="공지", description="지정한 채널에 깔끔한 공식 공지사항을 올립니다. (관리자 전용)")
@app_commands.checks.has_permissions(manage_messages=True)
async def slash_announce(interaction: discord.Interaction, channel: discord.TextChannel, title: str, content: str):
    embed = discord.Embed(
        title=f"📢 {title}",
        description=content,
        color=0xFFD700
    )
    embed.set_footer(text=f"작성자: {interaction.user.display_name}", icon_url=interaction.user.display_avatar.url)
    await channel.send(embed=embed)
    await interaction.response.send_message(f"✅ {channel.mention} 채널에 공지사항을 등록했습니다!", ephemeral=True)

@bot.tree.command(name="경고", description="규칙 위반 유저에게 누적 경고를 부여합니다. (관리자 전용)")
@app_commands.checks.has_permissions(manage_messages=True)
async def slash_warn(interaction: discord.Interaction, member: discord.Member, reason: str):
    user_id = member.id
    user_warnings[user_id] = user_warnings.get(user_id, 0) + 1
    count = user_warnings[user_id]
    
    embed = discord.Embed(
        title="⚠️ VIP 서버 경고 안내",
        description=f"{member.mention}님에게 경고가 부여되었습니다.",
        color=0xFFA500
    )
    embed.add_field(name="사유", value=reason, inline=True)
    embed.add_field(name="누적 경고", value=f"**{count}회** / 3회", inline=True)
    
    if count >= 3:
        embed.add_field(name="🚨 3회 누적 안내", value="경고가 3회 누적되었습니다. 추가 제재(`/타임아웃` 또는 `/제재`)를 검토해 주세요.", inline=False)
        
    embed.set_footer(text=f"담당 운영진: {interaction.user.display_name}")
    await interaction.response.send_message(embed=embed)

@bot.tree.command(name="타임아웃", description="유저를 지정한 시간(분) 동안 채팅 금지 처리합니다. (관리자 전용)")
@app_commands.checks.has_permissions(moderate_members=True)
async def slash_timeout(interaction: discord.Interaction, member: discord.Member, minutes: int, reason: str):
    if minutes < 1 or minutes > 10080:
        await interaction.response.send_message("❌ 1분에서 최대 10080분(7일) 사이로 입력해 주세요.", ephemeral=True)
        return
        
    duration = datetime.timedelta(minutes=minutes)
    await member.timeout(duration, reason=reason)
    
    embed = discord.Embed(
        title="🔇 타임아웃(채팅 금지) 조치",
        description=f"{member.mention}님이 **{minutes}분** 동안 타임아웃 처리되었습니다.",
        color=0xE74C3C
    )
    embed.add_field(name="사유", value=reason, inline=False)
    embed.set_footer(text=f"처리 관리자: {interaction.user.display_name}")
    await interaction.response.send_message(embed=embed)

@bot.tree.command(name="제재", description="규칙을 위반한 유저에 대한 제재 기록을 남깁니다. (관리자 전용)")
@app_commands.checks.has_permissions(manage_messages=True)
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

@bot.tree.command(name="청소", description="채팅창의 메시지를 지정한 개수만큼 한 번에 삭제합니다. (관리자 전용)")
@app_commands.checks.has_permissions(manage_messages=True)
async def slash_clear(interaction: discord.Interaction, amount: int):
    if amount < 1 or amount > 100:
        await interaction.response.send_message("❌ 1개에서 100개 사이의 숫자만 입력할 수 있습니다.", ephemeral=True)
        return
    await interaction.response.defer(ephemeral=True)
    deleted = await interaction.channel.purge(limit=amount)
    await interaction.followup.send(f"🧹 최근 메시지 **{len(deleted)}개**를 깔끔하게 삭제했습니다.", ephemeral=True)

# ----------------- 🔍 3. 있으면 편한 서버/유저 편의 기능 -----------------

@bot.tree.command(name="유저정보", description="멤버의 가입일, 계정 생성일, 보유 역할을 확인합니다.")
async def slash_userinfo(interaction: discord.Interaction, member: discord.Member = None):
    target = member or interaction.user
    roles = [role.mention for role in target.roles if role.name != "@everyone"]
    roles_str = ", ".join(roles) if roles else "없음"
    
    embed = discord.Embed(
        title=f"👤 {target.display_name}님의 정보",
        color=0x3498DB
    )
    embed.set_thumbnail(url=target.display_avatar.url)
    embed.add_field(name="디스코드 계정 생성일", value=target.created_at.strftime("%Y-%m-%d"), inline=True)
    embed.add_field(name="서버 가입일", value=target.joined_at.strftime("%Y-%m-%d") if target.joined_at else "알 수 없음", inline=True)
    embed.add_field(name="누적 경고", value=f"{user_warnings.get(target.id, 0)}회", inline=True)
    embed.add_field(name=f"보유 역할 ({len(roles)}개)", value=roles_str, inline=False)
    await interaction.response.send_message(embed=embed)

@bot.tree.command(name="서버정보", description="현재 서버의 인원수와 주요 현황을 확인합니다.")
async def slash_serverinfo(interaction: discord.Interaction):
    guild = interaction.guild
    embed = discord.Embed(
        title=f"👑 {guild.name} 서버 현황",
        color=0xFFD700
    )
    if guild.icon:
        embed.set_thumbnail(url=guild.icon.url)
    embed.add_field(name="서버 주인", value=guild.owner.mention if guild.owner else "알 수 없음", inline=True)
    embed.add_field(name="전체 멤버 수", value=f"**{guild.member_count}명**", inline=True)
    embed.add_field(name="서버 개설일", value=guild.created_at.strftime("%Y-%m-%d"), inline=True)
    embed.add_field(name="부스트 레벨", value=f"레벨 {guild.premium_tier} ({guild.premium_subscription_count}부스트)", inline=False)
    await interaction.response.send_message(embed=embed)

@bot.tree.command(name="투표만들기", description="찬성/반대 투표를 빠르게 생성합니다.")
async def slash_poll(interaction: discord.Interaction, topic: str):
    embed = discord.Embed(
        title="📊 서버 투표 안내",
        description=f"**주제:** {topic}\n\n⭕ 찬성  |  ❌ 반대",
        color=0x3498DB
    )
    embed.set_footer(text=f"개설자: {interaction.user.display_name}")
    await interaction.response.send_message(embed=embed)
    msg = await interaction.original_response()
    await msg.add_reaction("⭕")
    await msg.add_reaction("❌")

@bot.tree.command(name="말하기", description="입력한 내용을 깔끔한 임베드 박스로 대신 전송합니다.")
async def slash_say(interaction: discord.Interaction, message: str):
    embed = discord.Embed(description=message, color=0x00FF00)
    embed.set_author(name=interaction.user.display_name, icon_url=interaction.user.display_avatar.url)
    await interaction.response.send_message(embed=embed)

# ----------------- 🎵 4. 빅뱅 팬덤 & 미니게임 기능 -----------------

@bot.tree.command(name="오늘의추천", description="오늘의 빅뱅 추천곡을 수동으로 뽑습니다!")
async def slash_recommend_song(interaction: discord.Interaction):
    songs = load_songs()
    history = load_history()
    available_songs = [s for s in songs if s['title'] not in history]
    
    if not available_songs:
        history = []
        available_songs = songs
        
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

@bot.tree.command(name="명언", description="빅뱅 & 지드래곤의 레전드 명언과 명대사를 소환합니다.")
async def slash_quotes(interaction: discord.Interaction):
    quotes = [
        "기적을 믿지 마세요, 노력을 믿으세요.",
        "정신 차려, 이 각박한 세상 속에서.",
        "실패는 성공의 어머니가 아니라, 성공의 하녀일 뿐이다.",
        "내가 만든 길을 걸어갈 뿐이야.",
        "남들의 시선에 갇히지 말고 너만의 색깔로 그려.",
        "처음부터 잘하는 사람은 없어요. 그냥 미친 듯이 하는 거죠."
    ]
    embed = discord.Embed(
        title="👑 VIP Lounge 명언 릴레이",
        description=f"✨ *\"{random.choice(quotes)}\"*",
        color=0x111111
    )
    embed.set_footer(text="BIGBANG IS V.I.P")
    await interaction.response.send_message(embed=embed)

@bot.tree.command(name="빅뱅퀴즈", description="랜덤 빅뱅 팬덤 퀴즈를 출제합니다!")
async def slash_quiz(interaction: discord.Interaction):
    quizzes = [
        {"q": "빅뱅의 공식 데뷔일은 언제일까요?", "a": "2006년 8월 19일"},
        {"q": "빅뱅의 공식 응원봉 이름은 무엇일까요?", "a": "뱅봉 (왕관봉)"},
        {"q": "지드래곤이 직접 디자인에 참여한 빅뱅 응원봉의 상징 모양은?", "a": "왕관"},
        {"q": "2007년 발매되어 전국민적인 신드롬을 일으킨 빅뱅의 대표 메가히트곡은?", "a": "거짓말"},
        {"q": "빅뱅의 공식 팬클럽 이름은 무엇일까요?", "a": "V.I.P (VIP)"}
    ]
    quiz = random.choice(quizzes)
    embed = discord.Embed(
        title="❓ VIP 팬덤 능력고사 퀴즈!",
        description=f"**문제:** {quiz['q']}\n\n정답은 아래 스포일러를 클릭해 확인하세요!\n|| 정답: **{quiz['a']}** ||",
        color=0xFFD700
    )
    await interaction.response.send_message(embed=embed)

@bot.tree.command(name="최애투표", description="오늘의 최애 멤버 인기투표를 생성합니다.")
async def slash_bias_poll(interaction: discord.Interaction):
    embed = discord.Embed(
        title="💛 오늘 당신의 최애 멤버는?",
        description="아래 이모지를 눌러 투표에 참여해 주세요!\n\n🐉 **G-DRAGON**\n🌞 **태양 (TAEYANG)**\n👼 **대성 (DAESUNG)**",
        color=0xFFD700
    )
    await interaction.response.send_message(embed=embed)
    msg = await interaction.original_response()
    for emoji in ["🐉", "🌞", "👼"]:
        await msg.add_reaction(emoji)

@bot.tree.command(name="운세", description="오늘의 VIP 덕질 운세를 확인합니다.")
async def slash_fortune(interaction: discord.Interaction):
    fortunes = [
        "🌟 대길: 오늘 최애의 떡밥이나 레전드 직캠을 발견할 확률 200%!",
        "🎵 길: 우연히 들른 카페나 길거리에서 빅뱅 노래가 흘러나올 운세!",
        "💛 행운: 굿즈나 포토카드 교환/구매에서 엄청난 행운이 따릅니다.",
        "🔥 열정: 오늘은 빅뱅 콘서트 라이브 영상 정주행하기 딱 좋은 날!",
        "🍀 평온: 좋아하는 노래 들으며 기분 좋게 하루를 마무리할 수 있어요."
    ]
    embed = discord.Embed(
        title=f"🔮 {interaction.user.display_name}님의 오늘의 VIP 운세",
        description=random.choice(fortunes),
        color=0x9B59B6
    )
    await interaction.response.send_message(embed=embed)

@bot.tree.command(name="주사위", description="1부터 100 사이의 랜덤 주사위를 굴립니다.")
async def slash_dice(interaction: discord.Interaction):
    num = random.randint(1, 100)
    await interaction.response.send_message(f"🎲 **{interaction.user.display_name}**님이 주사위를 굴려 **{num}**이(가) 나왔습니다!")

# 관리자 전용 명령어 권한 에러 통합 처리
@slash_announce.error
@slash_warn.error
@slash_timeout.error
@slash_sanction.error
@slash_clear.error
@slash_clock_in.error
@slash_clock_out.error
@slash_away.error
@slash_back.error
async def admin_error(interaction: discord.Interaction, error):
    if isinstance(error, app_commands.MissingPermissions):
        await interaction.response.send_message("❌ 이 명령어는 운영진 권한이 있는 관리자만 사용할 수 있습니다.", ephemeral=True)

# ----------------- ⏰ 하루 2번(오전 8시, 오후 3시) 자동 추천 태스크 -----------------

@tasks.loop(time=[
    datetime.time(hour=8, minute=0, tzinfo=ZoneInfo("Asia/Seoul")),
    datetime.time(hour=15, minute=0, tzinfo=ZoneInfo("Asia/Seoul"))
])
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
            description=f"이번 시간에 추천해 드릴 곡은 **{song['title']}** 입니다!",
            color=0xFFD700
        )
        embed.add_field(name="YouTube 링크", value=song['url'], inline=False)
        await channel.send(embed=embed)

@daily_bigbang_song.before_loop
async def before_daily_song():
    await bot.wait_until_ready()

if __name__ == "__main__":
    keep_alive()
    bot.run(BOT_TOKEN)
