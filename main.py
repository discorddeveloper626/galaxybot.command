import os
import io
import aiohttp
import psutil
import discord
from discord import app_commands, Interaction, Embed
from discord.ext import commands, tasks
from dotenv import load_dotenv
from datetime import datetime, timezone, timedelta
from functools import wraps
from keep_alive import keep_alive

load_dotenv()

intents = discord.Intents.all()
bot = commands.Bot(command_prefix="!", intents=intents)

jst = timezone(timedelta(hours=9))
start_time = datetime.utcnow()

def is_admin():
    def decorator(func):
        @wraps(func)
        async def wrapper(interaction: discord.Interaction, *args, **kwargs):
            if not interaction.user.guild_permissions.administrator:
                await interaction.response.send_message("このコマンドは管理者のみ実行できます。", ephemeral=True)
                return
            return await func(interaction, *args, **kwargs)
        return wrapper
    return decorator

@bot.tree.command(name="avatar", description="ユーザーアバターを表示します。")
async def avatar(interaction: discord.Interaction, user: discord.User):
    avatar_url = user.avatar.url
    embed = discord.Embed(description=f"## {user.mention} さんのアバター", color=discord.Color.blue())
    embed.set_image(url=avatar_url)
    await interaction.response.send_message(embed=embed, ephemeral=True)

@bot.tree.command(name="ban", description="指定したユーザーをBANします（管理者限定）")
@is_admin()
@app_commands.describe(user="BANするユーザー", reason="BANの理由（任意）")
async def ban_user(interaction: discord.Interaction, user: discord.Member, reason: str = None):
    try:
        await user.ban(reason=reason)
        msg = f"{user.mention} をBANしました。"
        if reason:
            msg += f" 理由：{reason}"
        await interaction.response.send_message(msg, ephemeral=True)
    except Exception as e:
        await interaction.response.send_message(f"エラー: {e}", ephemeral=True)

@bot.tree.command(name="kick", description="指定したユーザーをキックします（管理者限定）")
@is_admin()
@app_commands.describe(user="キックするユーザー", reason="キックの理由（任意）")
async def kick_user(interaction: discord.Interaction, user: discord.Member, reason: str = None):
    try:
        await user.kick(reason=reason)
        msg = f"{user.mention} をキックしました。"
        if reason:
            msg += f" 理由：{reason}"
        await interaction.response.send_message(msg, ephemeral=True)
    except Exception as e:
        await interaction.response.send_message(f"エラー: {e}", ephemeral=True)

class EmbedModal(discord.ui.Modal, title="埋め込みメッセージ作成"):
    title_input = discord.ui.TextInput(label="タイトル", placeholder="埋め込みに表示されるタイトル", max_length=256, required=False)
    description_input = discord.ui.TextInput(label="説明", style=discord.TextStyle.paragraph, placeholder="埋め込みに表示される説明欄", max_length=2000)
    image_url_input = discord.ui.TextInput(label="画像", placeholder="埋め込みに表示される画像のURL", max_length=1000, required=False)

    async def on_submit(self, interaction: discord.Interaction):
        embed = discord.Embed(title=self.title_input.value, description=self.description_input.value, color=discord.Color.blue())
        if self.image_url_input.value:
            embed.set_image(url=self.image_url_input.value)
        embed.set_footer(text=interaction.user.display_name, icon_url=interaction.user.display_avatar.url)
        await interaction.response.send_message("埋め込みメッセージを送信しました！", ephemeral=True)
        await interaction.channel.send(embed=embed)

@bot.tree.command(name="embed", description="埋め込みメッセージを作成します。")
async def embed_command(interaction: discord.Interaction):
    await interaction.response.send_modal(EmbedModal())

class EmojiCopyModal(discord.ui.Modal, title="絵文字IDを入力"):
    emoji_id = discord.ui.TextInput(label="絵文字ID", placeholder="例: 123456789012345678", required=True)

    async def on_submit(self, interaction: discord.Interaction):
        emoji_id = self.emoji_id.value.strip()
        guild = interaction.guild
        if not guild:
            await interaction.response.send_message("このコマンドはサーバー内で使用してください。", ephemeral=True)
            return
        try:
            emoji_url = f"https://cdn.discordapp.com/emojis/{emoji_id}.gif"
            async with aiohttp.ClientSession() as session:
                async with session.get(emoji_url) as resp:
                    if resp.status == 200:
                        image_data = await resp.read()
                    else:
                        emoji_url = f"https://cdn.discordapp.com/emojis/{emoji_id}.png"
                        async with session.get(emoji_url) as resp:
                            if resp.status != 200:
                                raise ValueError("無効な絵文字IDか、絵文字が存在しません。")
                            image_data = await resp.read()
            image_file = io.BytesIO(image_data)
            new_emoji = await guild.create_custom_emoji(name=f"emoji_{emoji_id}", image=image_file.getvalue())
            await interaction.response.send_message(f"絵文字 {new_emoji} が追加されました！", ephemeral=True)
        except Exception as e:
            await interaction.response.send_message(f"エラーが発生しました: {e}", ephemeral=True)

@bot.tree.command(name="emoji-copy", description="絵文字IDを使って絵文字をコピーします。")
async def emoji_copy(interaction: discord.Interaction):
    await interaction.response.send_modal(EmojiCopyModal())

class VerifyButton(discord.ui.Button):
    def __init__(self, role_id: int):
        super().__init__(style=discord.ButtonStyle.success, label="✅ 認証/Verify", custom_id=f"verify_{role_id}")
        self.role_id = role_id

    async def callback(self, interaction: discord.Interaction):
        guild = interaction.guild
        member = interaction.user
        role = guild.get_role(self.role_id)
        if not role:
            await interaction.response.send_message("ロールが見つかりません。", ephemeral=True)
            return
        if role in member.roles:
            await interaction.response.send_message("あなたはすでに認証しています。", ephemeral=True)
        else:
            await member.add_roles(role)
            await interaction.response.send_message("認証が完了しました！", ephemeral=True)

class VerifyView(discord.ui.View):
    def __init__(self, role_id: int):
        super().__init__(timeout=None)
        self.add_item(VerifyButton(role_id))

@bot.tree.command(name="verify", description="認証パネルを作成します")
@app_commands.describe(role="付与するロール", description="認証パネルの説明", image_url="埋め込む画像URL")
async def verify(interaction: discord.Interaction, role: discord.Role, description: str, image_url: str = None):
    if not interaction.user.guild_permissions.administrator:
        await interaction.response.send_message("このコマンドを使用するには管理者権限が必要です。", ephemeral=True)
        return
    embed = discord.Embed(title="認証パネル", description=description, color=discord.Color.green())
    if image_url:
        embed.set_image(url=image_url)
    view = VerifyView(role.id)
    await interaction.response.send_message(embed=embed, view=view)
    bot.add_view(view)

@tasks.loop(seconds=15)
async def update_status():
    cpu = psutil.cpu_percent()
    gpu = 35  # 仮の値、GPU利用率取得したいなら別途ライブラリ
    total_guilds = len(bot.guilds)
    status_list = [
        discord.Activity(type=discord.ActivityType.watching, name="導入よろしくお願いします！"),
        discord.Activity(type=discord.ActivityType.competing, name=f"{total_guilds} Serversに参戦中"),
        discord.Activity(type=discord.ActivityType.watching, name=f"CPU {cpu}% / GPU {gpu}% を視聴中")
    ]
    await bot.change_presence(activity=status_list[update_status.current % len(status_list)])
    update_status.current += 1

update_status.current = 0

@bot.event
async def on_ready():
    print(f"✅ {bot.user} 起動完了")
    for guild in bot.guilds:
        for role in guild.roles:
            bot.add_view(VerifyView(role.id))
    update_status.start()

DISCORD_TOKEN = os.getenv("DISCORD_TOKEN")
if not DISCORD_TOKEN:
    print("❌ DISCORD_TOKEN が .env に設定されていません。")
else:
    print("🚀 Botが起動します。")

keep_alive()
bot.run(DISCORD_TOKEN)
