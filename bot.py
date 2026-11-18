import os
import json
import random
import datetime
import sqlite3
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

# ----------------- 디스코드 봇 설정 & DB 초기화 -----------------

intents = discord.Intents.default()
intents.message_content = True
intents.members = True  # 새 멤버 입장 감지 및 유저정보 조회용 필수 권한
bot = commands.Bot(command_prefix="!", intents=intents)

CHANNEL_ID = 1566416489270087843          # 🎵 오늘의 추천곡을 받을 채널 ID
WELCOME_CHANNEL_ID = 1566415614057127936  # 🎉 새 멤버 환영 인사를 보낼 채널 ID
BOT_TOKEN = os.environ.get("BOT_TOKEN")

# SQLite 영구 데이터베이스 세팅 (출근 기록, 누적 횟수, 상세 경고 로그)
db_conn = sqlite3.connect("vip_bot.db", check_same_thread=False)
db_cursor = db_conn.cursor()

db_cursor.execute("""
CREATE TABLE IF NOT EXISTS work_records (
    user_id INTEGER PRIMARY KEY,
    start_time TEXT,
    away_start TEXT,
    total_away_seconds INTEGER
)
""")

db_cursor.execute("""
CREATE TABLE IF NOT EXISTS warnings (
    user_id INTEGER PRIMARY KEY,
    warning_count INTEGER
)
""")

db_cursor.execute("""
CREATE TABLE IF NOT EXISTS warning_logs (
    log_id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER,
    moderator_name TEXT,
    reason TEXT,
    timestamp TEXT
)
""")
db_conn.commit()

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

# ----------------- 🎉 새 멤버 자동 환영 이벤트 (채널 분리 완료) -----------------

@bot.event
async def on_member_join(member: discord.Member):
    channel = bot.get_channel(WELCOME_CHANNEL_ID)
    if channel is not None:
        created_at_str = member.created_at.strftime("%Y-%m-%d")
        joined_at_str = member.joined_at.strftime("%Y-%m-%d %H:%M") if member.joined_at else "알 수 없음"
        
        embed = discord.Embed(
            title="👑 WELCOME TO VIP UNIVERSE!",
            description=f"{member.mention}님, **{member.guild.name}**에 오신 것을 진심으로 환영합니다! 💛\n\n"
                        f"당신은 우리 서버의 **{member.guild.member_count}번째** VIP 멤버입니다!\n"
                        f"공지사항과 규칙을 꼭 확인해 주시고, 다 함께 즐겁게 소통해요! 🎶",
            color=0xFFD700
        )
        embed.set_thumbnail(url=member.display_avatar.url)
        embed.add_field(name="📅 디스코드 계정 생성일", value=created_at_str, inline=True)
        embed.add_field(name="✨ 서버 가입일시", value=joined_at_str, inline=True)
        embed.set_footer(text="VIP UNIVERSE 서버 입장 관리 시스템")
        
        await channel.send(content=f"🎉 새로운 vip의 등장입니다! 모두들 반겨줍시다! {member.mention}", embed=embed)

# ----------------- 💼 1. 영구 DB 연동 출퇴근 & 자리비움 & 근무자목록 -----------------

@bot.tree.command(name="출근", description="운영진 출근 기록을 남깁니다. (관리자 전용)")
@app_commands.checks.has_permissions(manage_messages=True)
async def slash_clock_in(interaction: discord.Interaction):
    user_id = interaction.user.id
    now = datetime.datetime.now(ZoneInfo("Asia/Seoul"))
    
    db_cursor.execute("SELECT start_time FROM work_records WHERE user_id = ?", (user_id,))
    row = db_cursor.fetchone()
    
    if row:
        await interaction.response.send_message(
            f"⚠️ **{interaction.user.display_name}**님은 이미 출근 처리가 되어 있습니다! 먼저 `/퇴근`을 해주세요.",
            ephemeral=True
        )
        return

    time_str = now.strftime("%Y-%m-%d %H:%M:%S")
    db_cursor.execute(
        "INSERT INTO work_records (user_id, start_time, away_start, total_away_seconds) VALUES (?, ?, NULL, 0)",
        (user_id, time_str)
    )
    db_conn.commit()
    
    embed = discord.Embed(
        title="🟢 운영진 출근 로그",
        description=f"**{interaction.user.mention}**님이 업무를 시작했습니다.",
        color=0x2ECC71
    )
    embed.add_field(name="출근 시각", value=f"`{time_str}`", inline=False)
    embed.set_thumbnail(url=interaction.user.display_avatar.url)
    embed.set_footer(text="VIP 서버 운영팀 영구 근태 기록")
    await interaction.response.send_message(embed=embed)

@bot.tree.command(name="자리비움", description="근무 중 잠시 자리를 비울 때 기록합니다. (관리자 전용)")
@app_commands.checks.has_permissions(manage_messages=True)
async def slash_away(interaction: discord.Interaction, reason: str = "개인 용무"):
    user_id = interaction.user.id
    now_str = datetime.datetime.now(ZoneInfo("Asia/Seoul")).strftime("%Y-%m-%d %H:%M:%S")
    
    db_cursor.execute("SELECT start_time, away_start FROM work_records WHERE user_id = ?", (user_id,))
    row = db_cursor.fetchone()
    
    if not row:
        await interaction.response.send_message("❌ 먼저 `/출근`을 한 상태에서만 자리비움을 사용할 수 있습니다.", ephemeral=True)
        return
        
    if row[1] is not None:
        await interaction.response.send_message("⚠️ 이미 자리비움 상태입니다! 돌아오셨다면 `/복귀`를 눌러주세요.", ephemeral=True)
        return
        
    db_cursor.execute("UPDATE work_records SET away_start = ? WHERE user_id = ?", (now_str, user_id))
    db_conn.commit()
    
    embed = discord.Embed(
        title="🟡 운영진 자리비움 로그",
        description=f"**{interaction.user.mention}**님이 잠시 자리를 비웠습니다.",
        color=0xF1C40F
    )
    embed.add_field(name="자리비움 시각", value=f"`{now_str}`", inline=True)
    embed.add_field(name="사유", value=reason, inline=True)
    embed.set_footer(text="복귀 시 /복귀 명령어를 입력해 주세요.")
    await interaction.response.send_message(embed=embed)

@bot.tree.command(name="복귀", description="자리비움 상태를 해제하고 업무에 복귀합니다. (관리자 전용)")
@app_commands.checks.has_permissions(manage_messages=True)
async def slash_back(interaction: discord.Interaction):
    user_id = interaction.user.id
    now = datetime.datetime.now(ZoneInfo("Asia/Seoul"))
    
    db_cursor.execute("SELECT start_time, away_start, total_away_seconds FROM work_records WHERE user_id = ?", (user_id,))
    row = db_cursor.fetchone()
    
    if not row or row[1] is None:
        await interaction.response.send_message("❌ 현재 자리비움 상태가 아닙니다.", ephemeral=True)
        return
        
    away_start_dt = datetime.datetime.strptime(row[1], "%Y-%m-%d %H:%M:%S").replace(tzinfo=ZoneInfo("Asia/Seoul"))
    away_duration = int((now - away_start_dt).total_seconds())
    new_total_away = row[2] + away_duration
    
    db_cursor.execute("UPDATE work_records SET away_start = NULL, total_away_seconds = ? WHERE user_id = ?", (new_total_away, user_id))
    db_conn.commit()
    
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
    
    db_cursor.execute("SELECT start_time, away_start, total_away_seconds FROM work_records WHERE user_id = ?", (user_id,))
    row = db_cursor.fetchone()
    
    if not row:
        await interaction.response.send_message(
            f"❌ **{interaction.user.display_name}**님의 출근 기록이 없습니다! 먼저 `/출근`을 눌러주세요.",
            ephemeral=True
        )
        return

    start_dt = datetime.datetime.strptime(row[0], "%Y-%m-%d %H:%M:%S").replace(tzinfo=ZoneInfo("Asia/Seoul"))
    total_away = row[2]
    
    if row[1] is not None:
        away_start_dt = datetime.datetime.strptime(row[1], "%Y-%m-%d %H:%M:%S").replace(tzinfo=ZoneInfo("Asia/Seoul"))
        total_away += int((now - away_start_dt).total_seconds())
        
    total_elapsed = int((now - start_dt).total_seconds())
    actual_work = max(0, total_elapsed - total_away)
    
    db_cursor.execute("DELETE FROM work_records WHERE user_id = ?", (user_id,))
    db_conn.commit()
    
    embed = discord.Embed(
        title="🔴 운영진 퇴근 로그",
        description=f"**{interaction.user.mention}**님이 업무를 종료했습니다. 수고하셨습니다!",
        color=0xE74C3C
    )
    embed.add_field(name="출근 시각", value=f"`{start_dt.strftime('%H:%M:%S')}`", inline=True)
    embed.add_field(name="퇴근 시각", value=f"`{now.strftime('%H:%M:%S')}`", inline=True)
    embed.add_field(name="자리비움 합계", value=f"`{format_duration(total_away)}`", inline=True)
    embed.add_field(name="실제 순수 근무 시간", value=f"**{format_duration(actual_work)}**", inline=False)
    embed.set_thumbnail(url=interaction.user.display_avatar.url)
    embed.set_footer(text="VIP 서버 운영팀 근태 기록")
    await interaction.response.send_message(embed=embed)

@bot.tree.command(name="근무자목록", description="현재 출근 중인 운영진 목록과 근무 상태를 확인합니다. (관리자 전용)")
@app_commands.checks.has_permissions(manage_messages=True)
async def slash_working_list(interaction: discord.Interaction):
    db_cursor.execute("SELECT user_id, start_time, away_start, total_away_seconds FROM work_records")
    rows = db_cursor.fetchall()
    
    if not rows:
        await interaction.response.send_message("💤 현재 출근 중인 운영진이 없습니다.", ephemeral=True)
        return
        
    now = datetime.datetime.now(ZoneInfo("Asia/Seoul"))
    embed = discord.Embed(
        title="📋 현재 출근 중인 운영진 현황",
        description=f"총 **{len(rows)}명**의 운영진이 출근 상태입니다.",
        color=0x3498DB
    )
    
    for user_id, start_str, away_str, total_away in rows:
        member = interaction.guild.get_member(user_id)
        name = member.display_name if member else f"알 수 없는 운영진 ({user_id})"
        
        start_dt = datetime.datetime.strptime(start_str, "%Y-%m-%d %H:%M:%S").replace(tzinfo=ZoneInfo("Asia/Seoul"))
        current_away = total_away
        
        if away_str is not None:
            away_dt = datetime.datetime.strptime(away_str, "%Y-%m-%d %H:%M:%S").replace(tzinfo=ZoneInfo("Asia/Seoul"))
            current_away += int((now - away_dt).total_seconds())
            status_text = "🟡 자리비움 중"
        else:
            status_text = "🟢 근무 중"
            
        elapsed = int((now - start_dt).total_seconds())
        actual_work = max(0, elapsed - current_away)
        
        embed.add_field(
            name=f"{name} ({status_text})",
            value=f"• 출근 시각: `{start_dt.strftime('%H:%M:%S')}`\n• 순수 근무: **{format_duration(actual_work)}**",
            inline=False
        )
        
    embed.set_footer(text=f"조회 시각: {now.strftime('%Y-%m-%d %H:%M:%S')}")
    await interaction.response.send_message(embed=embed)

# ----------------- 🛡️ 2. 서버 관리 & 상세 로그 연동 경고 시스템 -----------------

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

@bot.tree.command(name="경고", description="유저에게 사유와 담당 운영진, 날짜가 포함된 영구 경고를 부여합니다. (관리자 전용)")
@app_commands.checks.has_permissions(manage_messages=True)
async def slash_warn(interaction: discord.Interaction, member: discord.Member, reason: str):
    user_id = member.id
    mod_name = interaction.user.display_name
    now_str = datetime.datetime.now(ZoneInfo("Asia/Seoul")).strftime("%Y-%m-%d %H:%M:%S")
    
    # 1. 누적 횟수 업데이트
    db_cursor.execute("SELECT warning_count FROM warnings WHERE user_id = ?", (user_id,))
    row = db_cursor.fetchone()
    current_count = row[0] if row else 0
    new_count = current_count + 1
    
    if row:
        db_cursor.execute("UPDATE warnings SET warning_count = ? WHERE user_id = ?", (new_count, user_id))
    else:
        db_cursor.execute("INSERT INTO warnings (user_id, warning_count) VALUES (?, ?)", (user_id, new_count))
        
    # 2. 상세 로그 기록 테이블에 추가
    db_cursor.execute(
        "INSERT INTO warning_logs (user_id, moderator_name, reason, timestamp) VALUES (?, ?, ?, ?)",
        (user_id, mod_name, reason, now_str)
    )
    db_conn.commit()
    
    embed = discord.Embed(
        title="⚠️ VIP 서버 경고 부여 안내",
        description=f"{member.mention}님에게 경고가 부여되었습니다.",
        color=0xFFA500
    )
    embed.add_field(name="위반 사유", value=reason, inline=False)
    embed.add_field(name="누적 경고", value=f"**{new_count}회** / 3회", inline=True)
    embed.add_field(name="담당 운영진", value=mod_name, inline=True)
    embed.add_field(name="부과 일시", value=f"`{now_str}`", inline=False)
    
    if new_count >= 3:
        embed.add_field(name="🚨 3회 누적 안내", value="경고가 3회 이상 누적되었습니다! `/타임아웃` 또는 `/제재` 조치를 고려해 주세요.", inline=False)
        
    embed.set_footer(text="VIP 서버 운영팀 경고 관리 시스템")
    await interaction.response.send_message(embed=embed)

@bot.tree.command(name="경고확인", description="특정 유저의 누적 경고 횟수를 조회합니다. (관리자 전용)")
@app_commands.checks.has_permissions(manage_messages=True)
async def slash_check_warn(interaction: discord.Interaction, member: discord.Member):
    db_cursor.execute("SELECT warning_count FROM warnings WHERE user_id = ?", (member.id,))
    row = db_cursor.fetchone()
    count = row[0] if row else 0
    
    await interaction.response.send_message(f"👤 **{member.display_name}**님의 누적 경고 횟수는 총 **{count}회** 입니다. (상세 내역은 `/경고내역`으로 확인)", ephemeral=True)

@bot.tree.command(name="경고내역", description="유저의 상세 경고 이력(사유, 담당자, 날짜)을 조회합니다. (관리자 전용)")
@app_commands.checks.has_permissions(manage_messages=True)
async def slash_warn_history(interaction: discord.Interaction, member: discord.Member):
    db_cursor.execute("SELECT moderator_name, reason, timestamp FROM warning_logs WHERE user_id = ? ORDER BY log_id DESC", (member.id,))
    rows = db_cursor.fetchall()
    
    db_cursor.execute("SELECT warning_count FROM warnings WHERE user_id = ?", (member.id,))
    w_row = db_cursor.fetchone()
    total_count = w_row[0] if w_row else 0

    if not rows:
        await interaction.response.send_message(f"✨ **{member.display_name}**님의 누적 경고 상세 이력이 없습니다!", ephemeral=True)
        return
        
    embed = discord.Embed(
        title=f"📜 {member.display_name}님의 경고 상세 이력",
        description=f"현재 총 누적 경고: **{total_count}회**",
        color=0xE67E22
    )
    
    for idx, (mod, reason, time_str) in enumerate(rows[:10], start=1): # 최근 10개까지 표시
        embed.add_field(
            name=f"#{idx} | 일시: {time_str}",
            value=f"• **사유:** {reason}\n• **담당 운영진:** {mod}",
            inline=False
        )
        
    if len(rows) > 10:
        embed.set_footer(text=f"최근 10건만 표시됨 (전체 이력: {len(rows)}건)")
    else:
        embed.set_footer(text="VIP 서버 운영팀 경고 관리 장부")
        
    await interaction.response.send_message(embed=embed)

@bot.tree.command(name="경고목록", description="현재 경고를 1회 이상 받은 전체 멤버 목록을 확인합니다. (관리자 전용)")
@app_commands.checks.has_permissions(manage_messages=True)
async def slash_warn_list(interaction: discord.Interaction):
    db_cursor.execute("SELECT user_id, warning_count FROM warnings WHERE warning_count > 0 ORDER BY warning_count DESC")
    rows = db_cursor.fetchall()
    
    if not rows:
        await interaction.response.send_message("✨ 현재 경고를 받은 멤버가 단 한 명도 없습니다!", ephemeral=True)
        return
        
    embed = discord.Embed(
        title="📋 VIP 서버 누적 경고 보유자 목록",
        description=f"현재 경고를 1회 이상 받은 인원은 총 **{len(rows)}명**입니다.",
        color=0xFFA500
    )
    
    lines = []
    for idx, (user_id, count) in enumerate(rows, start=1):
        member = interaction.guild.get_member(user_id)
        user_display = f"{member.mention} (`{member.display_name}`)" if member else f"서버 탈퇴 유저 (`ID: {user_id}`)"
        alert = " 🚨" if count >= 3 else ""
        lines.append(f"**{idx}.** {user_display} — **{count}회**{alert}")
        
    list_text = "\n".join(lines[:30])
    embed.add_field(name="경고 누적 현황 (높은 순)", value=list_text, inline=False)
    if len(rows) > 30:
        embed.set_footer(text=f"상위 30명까지 표시됨 (전체 {len(rows)}명)")
    else:
        embed.set_footer(text="VIP 서버 운영팀 경고 관리 장부")
        
    await interaction.response.send_message(embed=embed)

@bot.tree.command(name="경고차감", description="유저의 누적 경고를 지정한 횟수만큼 차감합니다. (관리자 전용)")
@app_commands.checks.has_permissions(manage_messages=True)
async def slash_reduce_warn(interaction: discord.Interaction, member: discord.Member, amount: int = 1, reason: str = "운영진 판단에 의한 차감"):
    if amount < 1:
        await interaction.response.send_message("❌ 차감할 횟수는 1 이상 입력해 주세요.", ephemeral=True)
        return

    db_cursor.execute("SELECT warning_count FROM warnings WHERE user_id = ?", (member.id,))
    row = db_cursor.fetchone()
    current_count = row[0] if row else 0

    if current_count == 0:
        await interaction.response.send_message(f"ℹ️ **{member.display_name}**님은 현재 누적 경고가 0회입니다.", ephemeral=True)
        return

    new_count = max(0, current_count - amount)
    if new_count == 0:
        db_cursor.execute("DELETE FROM warnings WHERE user_id = ?", (member.id,))
    else:
        db_cursor.execute("UPDATE warnings SET warning_count = ? WHERE user_id = ?", (new_count, member.id))
    db_conn.commit()

    embed = discord.Embed(
        title="🔽 VIP 서버 경고 차감 안내",
        description=f"{member.mention}님의 경고가 **{amount}회** 차감되었습니다.",
        color=0x2ECC71
    )
    embed.add_field(name="사유", value=reason, inline=True)
    embed.add_field(name="현재 누적 경고", value=f"**{new_count}회** (기존 {current_count}회)", inline=True)
    embed.set_footer(text=f"담당 운영진: {interaction.user.display_name}")
    await interaction.response.send_message(embed=embed)

@bot.tree.command(name="경고초기화", description="유저의 누적 경고와 상세 이력을 0회로 완전히 초기화합니다. (관리자 전용)")
@app_commands.checks.has_permissions(manage_messages=True)
async def slash_reset_warn(interaction: discord.Interaction, member: discord.Member, reason: str = "경고 기록 초기화"):
    db_cursor.execute("SELECT warning_count FROM warnings WHERE user_id = ?", (member.id,))
    row = db_cursor.fetchone()
    prev_count = row[0] if row else 0

    db_cursor.execute("DELETE FROM warnings WHERE user_id = ?", (member.id,))
    db_cursor.execute("DELETE FROM warning_logs WHERE user_id = ?", (member.id,))
    db_conn.commit()

    embed = discord.Embed(
        title="🔄 VIP 서버 경고 초기화 안내",
        description=f"{member.mention}님의 누적 경고 및 상세 이력 기록이 모두 초기화되었습니다.",
        color=0x3498DB
    )
    embed.add_field(name="사유", value=reason, inline=True)
    embed.add_field(name="초기화 전 경고", value=f"{prev_count}회", inline=True)
    embed.set_footer(text=f"담당 운영진: {interaction.user.display_name}")
    await interaction.response.send_message(embed=embed)

@bot.tree.command(name="타임아웃", description="유저를 지정한 시간(분) 동안 실제 채팅 금지 처리합니다. (관리자 전용)")
@app_commands.checks.has_permissions(moderate_members=True)
async def slash_timeout(interaction: discord.Interaction, member: discord.Member, minutes: int, reason: str):
    if minutes < 1 or minutes > 10080:
        await interaction.response.send_message("❌ 1분에서 최대 10080분(7일) 사이로 입력해 주세요.", ephemeral=True)
        return
        
    try:
        duration = datetime.timedelta(minutes=minutes)
        await member.timeout(duration, reason=reason)
    except discord.Forbidden:
        await interaction.response.send_message("❌ 권한이 부족하여 해당 관리자나 서버 주인을 타임아웃할 수 없습니다.", ephemeral=True)
        return

    embed = discord.Embed(
        title="🔇 타임아웃(채팅 금지) 조치 완료",
        description=f"{member.mention}님이 실제로 **{minutes}분** 동안 타임아웃 처리되었습니다.",
        color=0xE74C3C
    )
    embed.add_field(name="사유", value=reason, inline=False)
    embed.set_footer(text=f"처리 관리자: {interaction.user.display_name}")
    await interaction.response.send_message(embed=embed)

@bot.tree.command(name="제재", description="유저를 서버에서 실제로 강퇴하거나 차단합니다. (관리자 전용)")
@app_commands.checks.has_permissions(ban_members=True)
async def slash_sanction(interaction: discord.Interaction, member: discord.Member, action: str, reason: str):
    action_lower = action.lower()
    if action_lower not in ["강퇴", "추방", "차단", "ban", "kick"]:
        await interaction.response.send_message("❌ 올바른 제재 방식을 입력해 주세요 (예: `강퇴` 또는 `차단`)", ephemeral=True)
        return
        
    if member.guild_permissions.administrator or member == interaction.guild.owner:
        await interaction.response.send_message("❌ 관리자 권한을 가진 멤버나 서버 주인은 제재할 수 없습니다!", ephemeral=True)
        return

    try:
        embed = discord.Embed(
            title="🚨 VIP 서버 실제 제재 조치",
            color=0xFF0000
        )
        embed.add_field(name="대상 유저", value=member.mention, inline=True)
        embed.add_field(name="조치 내용", value=action, inline=True)
        embed.add_field(name="사유", value=reason, inline=False)
        embed.set_footer(text=f"처리 관리자: {interaction.user.name}")

        if action_lower in ["강퇴", "추방", "kick"]:
            await member.kick(reason=reason)
            embed.description = f"{member.mention}님이 서버에서 정상적으로 **추방(강퇴)** 되었습니다."
        else:
            await member.ban(reason=reason)
            embed.description = f"{member.mention}님이 서버에서 실제로 **차단(Ban)** 되었습니다."

        await interaction.response.send_message(embed=embed)
        
    except discord.Forbidden:
        await interaction.response.send_message("❌ 봇의 권한이 대상 멤버보다 낮거나 디스코드 보안 정책으로 인해 제재할 수 없습니다.", ephemeral=True)

@bot.tree.command(name="제재차감", description="타임아웃을 해제하거나 차단(Ban)된 유저 ID의 차단을 풀어줍니다. (관리자 전용)")
@app_commands.checks.has_permissions(ban_members=True)
async def slash_reduce_sanction(interaction: discord.Interaction, user_id: str, action: str, reason: str = "제재 완화 조치"):
    if not user_id.isdigit():
        await interaction.response.send_message("❌ 올바른 유저 ID 숫자(예: `123456789012345678`)를 입력해 주세요.", ephemeral=True)
        return

    target_id = int(user_id)
    action_lower = action.lower()

    if action_lower in ["타임아웃해제", "타임아웃", "timeout"]:
        member = interaction.guild.get_member(target_id)
        if not member:
            await interaction.response.send_message("❌ 현재 서버에 있는 멤버가 아닙니다.", ephemeral=True)
            return
        try:
            await member.timeout(None, reason=reason)
            embed = discord.Embed(
                title="🔓 타임아웃 해제 완료",
                description=f"{member.mention}님의 타임아웃(채팅 금지)이 해제되었습니다.",
                color=0x2ECC71
            )
            embed.add_field(name="사유", value=reason, inline=False)
            embed.set_footer(text=f"처리 관리자: {interaction.user.display_name}")
            await interaction.response.send_message(embed=embed)
        except discord.Forbidden:
            await interaction.response.send_message("❌ 권한이 부족하여 타임아웃을 해제할 수 없습니다.", ephemeral=True)

    elif action_lower in ["차단해제", "밴해제", "unban", "ban"]:
        try:
            user_obj = discord.Object(id=target_id)
            await interaction.guild.unban(user_obj, reason=reason)
            embed = discord.Embed(
                title="🕊️ 서버 차단(Ban) 해제 완료",
                description=f"유저 ID `{target_id}`의 서버 차단이 해제되었습니다. 이제 다시 서버에 들어올 수 있습니다.",
                color=0x2ECC71
            )
            embed.add_field(name="사유", value=reason, inline=False)
            embed.set_footer(text=f"처리 관리자: {interaction.user.display_name}")
            await interaction.response.send_message(embed=embed)
        except discord.NotFound:
            await interaction.response.send_message("❌ 해당 유저 ID는 현재 차단 목록에 없습니다.", ephemeral=True)
        except discord.Forbidden:
            await interaction.response.send_message("❌ 봇에게 차단 해제 권한이 부족합니다.", ephemeral=True)
    else:
        await interaction.response.send_message("❌ 해제 방식을 `타임아웃해제` 또는 `차단해제` 중 하나로 입력해 주세요.", ephemeral=True)

@bot.tree.command(name="제재초기화", description="유저의 누적 경고, 상세 이력, 타임아웃 제재를 모두 초기화합니다. (관리자 전용)")
@app_commands.checks.has_permissions(ban_members=True)
async def slash_reset_sanction(interaction: discord.Interaction, member: discord.Member, reason: str = "전체 제재 및 경고 초기화"):
    db_cursor.execute("DELETE FROM warnings WHERE user_id = ?", (member.id,))
    db_cursor.execute("DELETE FROM warning_logs WHERE user_id = ?", (member.id,))
    db_conn.commit()

    timeout_status = "해제 완료"
    try:
        if member.is_timed_out():
            await member.timeout(None, reason=reason)
        else:
            timeout_status = "해당 없음"
    except discord.Forbidden:
        timeout_status = "권한 부족으로 해제 실패"

    embed = discord.Embed(
        title="✨ VIP 서버 제재 및 경고 일괄 초기화",
        description=f"{member.mention}님의 모든 경고 누적, 상세 이력, 활성 제재가 깨끗하게 초기화되었습니다.",
        color=0x3498DB
    )
    embed.add_field(name="누적 경고", value="0회로 초기화", inline=True)
    embed.add_field(name="타임아웃 상태", value=timeout_status, inline=True)
    embed.add_field(name="사유", value=reason, inline=False)
    embed.set_footer(text=f"처리 관리자: {interaction.user.display_name}")
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

# ----------------- 🔍 3. 서버/유저 편의 기능 -----------------

@bot.tree.command(name="유저정보", description="멤버의 가입일, 계정 생성일, 누적 경고를 확인합니다.")
async def slash_userinfo(interaction: discord.Interaction, member: discord.Member = None):
    target = member or interaction.user
    roles = [role.mention for role in target.roles if role.name != "@everyone"]
    roles_str = ", ".join(roles) if roles else "없음"
    
    db_cursor.execute("SELECT warning_count FROM warnings WHERE user_id = ?", (target.id,))
    row = db_cursor.fetchone()
    warn_count = row[0] if row else 0
    
    embed = discord.Embed(
        title=f"👤 {target.display_name}님의 정보",
        color=0x3498DB
    )
    embed.set_thumbnail(url=target.display_avatar.url)
    embed.add_field(name="디스코드 계정 생성일", value=target.created_at.strftime("%Y-%m-%d"), inline=True)
    embed.add_field(name="서버 가입일", value=target.joined_at.strftime("%Y-%m-%d") if target.joined_at else "알 수 없음", inline=True)
    embed.add_field(name="누적 경고", value=f"{warn_count}회", inline=True)
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

# ----------------- 🎵 4. 빅뱅 팬덤 & 미니게임 기능 (동시성 안전 보완) -----------------

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

@bot.tree.command(name="빅뱅퀴즈", description="랜덤 빅뱅 팬덤 퀴즈를 출제합니다! (총 30문제)")
async def slash_quiz(interaction: discord.Interaction):
    quizzes = [
        # --- 기본 & 팬덤 상식 (1~10) ---
        {"q": "빅뱅의 공식 데뷔일은 언제일까요?", "a": "2006년 8월 19일"},
        {"q": "빅뱅의 공식 팬클럽 이름은 무엇일까요?", "a": "V.I.P (VIP)"},
        {"q": "빅뱅의 공식 응원봉 이름은 무엇일까요?", "a": "뱅봉 (왕관봉)"},
        {"q": "지드래곤이 직접 디자인에 참여한 빅뱅 응원봉의 상징 모양은?", "a": "왕관"},
        {"q": "빅뱅의 리더를 맡고 있는 멤버는 누구일까요?", "a": "지드래곤 (G-DRAGON)"},
        {"q": "멤버 지드래곤(G-DRAGON)의 본명은 무엇일까요?", "a": "권지용"},
        {"q": "멤버 태양(TAEYANG)의 본명은 무엇일까요?", "a": "동영배"},
        {"q": "멤버 대성(DAESUNG)의 본명은 무엇일까요?", "a": "강대성"},
        {"q": "빅뱅 멤버들 중 막내라인에 속하며 보컬과 예능감을 담당하는 멤버는?", "a": "대성"},
        {"q": "빅뱅이 처음 결성될 때 방영되었던 다큐멘터리 프로그램의 제목은?", "a": "리얼다큐 빅뱅"},

        # --- 앨범 & 히트곡 (11~20) ---
        {"q": "2007년 발매되어 전국민적인 신드롬을 일으킨 빅뱅의 대표 메가히트곡은?", "a": "거짓말"},
        {"q": "2008년 발매된 '하루하루'의 뮤직비디오에서 시한부 연기를 펼친 여주인공 배우는?", "a": "박민영"},
        {"q": "빅뱅의 첫 번째 정규 앨범(1집) 타이틀 곡은 무엇일까요?", "a": "BIGBANG (La La La)"},
        {"q": "2012년 발매되어 '붐샤칼라카' 열풍을 일으킨 곡이 수록된 미니앨범 이름은?", "a": "ALIVE"},
        {"q": "2015년 매달 신곡을 발표하며 가요계를 휩쓴 빅뱅의 싱글 프로젝트 시리즈 이름은?", "a": "MADE"},
        {"q": "2015년 멜론 연간 차트 1위를 차지한 빅뱅의 대표 댄스곡은?", "a": "뱅뱅뱅 (BANG BANG BANG)"},
        {"q": "2018년 군 입대 전 팬들을 위해 깜짝 발표한 디지털 싱글의 제목은?", "a": "꽃길 (FLOWER ROAD)"},
        {"q": "2022년 4월 4일 4년 만에 컴백하며 발표한 서정적인 감성의 곡 제목은?", "a": "봄여름가을겨울 (Still Life)"},
        {"q": "이문세의 명곡을 빅뱅만의 스타일로 리메이크해 큰 사랑을 받은 곡은?", "a": "붉은 노을"},
        {"q": "빅뱅 정규 3집 《MADE》의 더블 타이틀곡은 '에라 모르겠다'와 무엇일까요?", "a": "LAST DANCE"},

        # --- 솔로 활동 & 레전드 무대 (21~30) ---
        {"q": "지드래곤의 첫 번째 솔로 정규 앨범이자 메가히트곡의 제목은?", "a": "Heartbreaker (하트브레이커)"},
        {"q": "2024년 10월 지드래곤이 7년 4개월 만에 발표한 솔로 디지털 싱글 제목은?", "a": "POWER"},
        {"q": "지드래곤의 곡으로 태양과 대성이 피처링에 참여해 2024 MAMA 무대를 뒤집어놓은 곡은?", "a": "HOME SWEET HOME"},
        {"q": "태양의 대표 솔로 발라드곡으로 수많은 가수들이 커버한 명곡은?", "a": "눈, 코, 입"},
        {"q": "지드래곤과 태양이 결성한 힙합 유닛 'GD X TAEYANG'의 대표곡은?", "a": "GOOD BOY"},
        {"q": "대성이 2008년 발매하여 전 세대에게 사랑받은 트로트 데뷔곡은?", "a": "날 봐, 귀순"},
        {"q": "대성이 운영하고 있는 개인 유튜브 채널의 이름은 무엇일까요?", "a": "집대성"},
        {"q": "지드래곤이 '무한도전' 영동고속도로 가요제에서 박명수와 함께 부른 곡은?", "a": "바람났어"},
        {"q": "태양이 솔로 미니 2집에서 방탄소년단(BTS) 지민과 협업해 발표한 곡은?", "a": "VIBE"},
        {"q": "지드래곤이 론칭한 본인의 패션 브랜드 이름은 무엇일까요?", "a": "피스마이너스원 (PEACEMINUSONE)"}
    ]
    quiz = random.choice(quizzes)
    embed = discord.Embed(
        title="❓ VIP 팬덤 능력고사 퀴즈!",
        description=f"**문제:** {quiz['q']}\n\n정답은 아래 스포일러를 클릭해 확인하세요!\n|| 정답: **{quiz['a']}** ||",
        color=0xFFD700
    )
    embed.set_footer(text=f"총 {len(quizzes)}문제 중 랜덤 출제")
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
@slash_check_warn.error
@slash_warn_list.error
@slash_warn_history.error
@slash_reduce_warn.error
@slash_reset_warn.error
@slash_timeout.error
@slash_sanction.error
@slash_reduce_sanction.error
@slash_reset_sanction.error
@slash_clear.error
@slash_clock_in.error
@slash_clock_out.error
@slash_away.error
@slash_back.error
@slash_working_list.error
async def admin_error(interaction: discord.Interaction, error):
    if isinstance(error, app_commands.MissingPermissions):
        await interaction.response.send_message("❌ 이 명령어는 운영진 권한이 있는 관리자만 사용할 수 있습니다.", ephemeral=True)

# ----------------- ⏰ 하루 2번(오전 8시, 오후 3시) 자동 추천 태스크 (동시성 보완) -----------------

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
