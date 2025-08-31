import discord
from discord.ext import commands
from discord.ui import View, Button, Modal, TextInput, Select
import os, asyncio
from keep_alive import keep_alive
from replit.database import Database

# Uruchamia serwer internetowy, który zapobiega uśpieniu bota
keep_alive()

TOKEN = os.getenv("DISCORD_TOKEN")
db = Database(os.getenv("REPLIT_DB_URL"))

intents = discord.Intents.all()
bot = commands.Bot(command_prefix="!", intents=intents)

# ===== Formularz Ticketa =====
class TicketModal(Modal, title="Formularz Ticketa"):
    nick = TextInput(label="Twój nick w Minecraft", placeholder="np. Kowalski123", required=True)

    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        guild = interaction.guild

        # Podstawowe uprawnienia
        overwrites = {
            guild.default_role: discord.PermissionOverwrite(read_messages=False),
            interaction.user: discord.PermissionOverwrite(read_messages=True, send_messages=True),
            guild.me: discord.PermissionOverwrite(read_messages=True, send_messages=True)
        }

        # Sprawdź rolę do pingowania
        ping_role = None
        try:
            ping_role_id = db.get("ticket_ping_role")
            if ping_role_id:
                ping_role = guild.get_role(int(ping_role_id))
                if ping_role:
                    overwrites[ping_role] = discord.PermissionOverwrite(read_messages=True, send_messages=True)
                    print(f"✅ Dodano uprawnienia dla roli: {ping_role.name}")
        except Exception as e:
            print(f"⚠️ Błąd z rolą ping: {e}")

        # Próba utworzenia kanału
        try:
            print(f"🔄 Tworzenie kanału dla użytkownika: {interaction.user.name}")
            channel = await guild.create_text_channel(
                name=f"ticket-{interaction.user.name}".lower().replace(" ", "-"),
                overwrites=overwrites,
                reason=f"Ticket utworzony przez {interaction.user}"
            )
            print(f"✅ Kanał utworzony: {channel.name}")
        except discord.Forbidden as e:
            print(f"❌ Brak uprawnień: {e}")
            return await interaction.followup.send("❌ Bot nie ma uprawnień do tworzenia kanałów! Sprawdź uprawnienia bota.", ephemeral=True)
        except Exception as e:
            print(f"❌ Nieoczekiwany błąd: {e}")
            return await interaction.followup.send(f"❌ Błąd podczas tworzenia ticketa: {str(e)}", ephemeral=True)

        # Wyślij wiadomość w kanale
        try:
            mention_text = ping_role.mention if ping_role else "Nowy ticket!"

            embed = discord.Embed(title="🎟️ Ticket", color=discord.Color.green())
            embed.add_field(name="👤 Użytkownik", value=interaction.user.mention, inline=True)
            embed.add_field(name="🎮 Nick w Minecraft", value=self.nick.value, inline=False)
            embed.set_footer(text=f"ID Użytkownika: {interaction.user.id}")

            view = TicketControls()
            await channel.send(f"{mention_text}", embed=embed, view=view)
            await interaction.followup.send(f"✅ Ticket utworzony: {channel.mention}", ephemeral=True)
            print(f"✅ Ticket pomyślnie utworzony: {channel.name}")
        except Exception as e:
            print(f"❌ Błąd podczas wysyłania wiadomości: {e}")
            await interaction.followup.send("❌ Ticket utworzony, ale wystąpił błąd z wiadomością.", ephemeral=True)

# ===== Kontrolki Ticketa =====
class TicketControls(View):
    def __init__(self):
        super().__init__(timeout=None)
        self.claimed_by = None

    @discord.ui.button(label="🔒 Zamknij", style=discord.ButtonStyle.danger, custom_id="close_ticket_button")
    async def close_ticket(self, interaction: discord.Interaction, button: Button):
        await interaction.response.send_message("Ticket zostanie zamknięty za 5s...", ephemeral=True)
        await asyncio.sleep(5)
        await interaction.channel.delete()

    @discord.ui.button(label="✏️ Zmień nazwę", style=discord.ButtonStyle.primary, custom_id="rename_ticket_button")
    async def rename_ticket(self, interaction: discord.Interaction, button: Button):
        if not interaction.user.guild_permissions.manage_channels:
            return await interaction.response.send_message("❌ Nie masz uprawnień do zmiany nazwy.", ephemeral=True)
        await interaction.response.send_modal(RenameModal())

    @discord.ui.button(label="📌 Odbierz", style=discord.ButtonStyle.success, custom_id="claim_ticket_button")
    async def claim_ticket(self, interaction: discord.Interaction, button: Button):
        if self.claimed_by:
            return await interaction.response.send_message(f"❌ Ticket już został odebrany przez <@{self.claimed_by}>", ephemeral=True)

        # Sprawdź uprawnienia
        try:
            ping_role_id = db.get("ticket_ping_role")
            if ping_role_id:
                ping_role = interaction.guild.get_role(int(ping_role_id))
                if ping_role and ping_role not in interaction.user.roles and not interaction.user.guild_permissions.manage_channels:
                    return await interaction.response.send_message("❌ Nie masz uprawnień, aby odebrać ten ticket.", ephemeral=True)
        except Exception as e:
            print(f"⚠️ Błąd sprawdzania uprawnień: {e}")

        self.claimed_by = interaction.user.id
        await interaction.response.send_message(f"✅ Ticket odebrany przez {interaction.user.mention}", ephemeral=False)
        button.disabled = True
        await interaction.message.edit(view=self)

# ===== Panel kategorii (2 testowe) =====
class CategorySelect(View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.select(
        placeholder="Wybierz kategorię",
        custom_id="category_select_menu",
        options=[
            discord.SelectOption(label="Kupno", description="Ticket związany z kupnem"),
            discord.SelectOption(label="Sprzedaż", description="Ticket związany ze sprzedażą")
        ]
    )
    async def select_category(self, interaction: discord.Interaction, select: discord.ui.Select):
        await interaction.response.send_modal(TicketModal())

# ===== Komendy =====
@bot.tree.command(name="setup_tickets", description="Wyślij panel ticketów")
@commands.has_permissions(administrator=True)
async def setup_tickets(interaction: discord.Interaction):
    embed = discord.Embed(
        title="🎟️ Centrum Pomocy",
        description="Wybierz kategorię, aby utworzyć ticket.",
        color=discord.Color.blue()
    )
    await interaction.channel.send(embed=embed, view=CategorySelect())
    await interaction.response.send_message("✅ Panel ticketów wysłany!", ephemeral=True)

@bot.tree.command(name="ustaw_role_ping", description="Ustaw rolę do pingowania przy nowym tickecie i będzie miała do nich dostęp.")
@commands.has_permissions(administrator=True)
async def ustaw_role_ping(interaction: discord.Interaction, rola: discord.Role):
    db.set("ticket_ping_role", rola.id)
    await interaction.response.send_message(f"✅ Rola do pingowania ustawiona na {rola.mention}", ephemeral=True)

# ===== Dodatkowe klasy i komendy =====
class RenameModal(Modal, title="Zmień nazwę ticketa"):
    new_name = TextInput(label="Nowa nazwa kanału", placeholder="np. ticket-nowa-nazwa", required=True)

    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        await interaction.channel.edit(name=self.new_name.value)
        await interaction.followup.send(f"✅ Nazwa ticketa zmieniona na: **{self.new_name.value}**", ephemeral=True)

@bot.tree.command(name="zmien_nazwe", description="Zmienia nazwę kanału ticketu.")
async def rename_command(interaction: discord.Interaction):
    if not interaction.user.guild_permissions.manage_channels:
        return await interaction.response.send_message("❌ Nie masz uprawnień do zmiany nazwy.", ephemeral=True)
    await interaction.response.send_modal(RenameModal())

@bot.event
async def on_ready():
    bot.add_view(CategorySelect())
    bot.add_view(TicketControls())
    print(f"✅ Zalogowano jako {bot.user}")
    await bot.tree.sync()

if TOKEN:
    bot.run(TOKEN)
else:
    print("❌ Brak tokena w Secrets!")
