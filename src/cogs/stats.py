import time
import discord
from discord.ext import commands
from discord import app_commands
import psutil

class Stats(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.start_time = time.time()

    @app_commands.command(name="resources", description="Shows current server usage and cool statistics.")
    async def resources(self, interaction: discord.Interaction):
        # Calculate uptime
        current_time = time.time()
        uptime_seconds = int(round(current_time - self.start_time))
        m, s = divmod(uptime_seconds, 60)
        h, m = divmod(m, 60)
        d, h = divmod(h, 24)
        uptime_str = f"{d}d {h}h {m}m {s}s"

        # Fetch system usage
        cpu_usage = psutil.cpu_percent(interval=None)
        ram = psutil.virtual_memory()
        ram_usage = ram.percent
        ram_total = round(ram.total / (1024**3), 2)
        ram_used = round(ram.used / (1024**3), 2)

        # Get total streams completed from bot
        total_streams = getattr(self.bot, 'total_streams_completed', 0)

        try:
            from version import get_release_info, check_github_update
            rel = get_release_info()
            ver_text = f"**{rel['tag']}** [{rel['codename']}]"
            update = await check_github_update()
            if update.get("has_update"):
                ver_text += f"\n:rocket: **Update Available: [{update['latest_version']}]({update['release_url']})**"
        except Exception:
            ver_text = "**v2.4.0**"

        # Build embed
        embed = discord.Embed(title="Bot Statistics & Resources", color=discord.Color.blue())
        embed.add_field(name="Release Version", value=ver_text, inline=False)
        embed.add_field(name="Uptime", value=uptime_str, inline=False)
        embed.add_field(name="CPU Usage", value=f"{cpu_usage}%", inline=True)
        embed.add_field(name="RAM Usage", value=f"{ram_usage}% ({ram_used}GB / {ram_total}GB)", inline=True)
        embed.add_field(name="Total Streams Completed", value=str(total_streams), inline=False)

        await interaction.response.send_message(embed=embed)

async def setup(bot):
    await bot.add_cog(Stats(bot))
