import discord
from discord.ext import commands
from discord.ui import View, Button, Modal, TextInput, Select
import os, asyncio
from replit.database import Database
from keep_alive import keep_alive # Importuje plik, który będzie utrzymywał bota online
import random

keep_alive() # Uruchamia serwer internetowy
TOKEN = os.getenv("DISCORD_TOKEN")
db = Database(os.getenv("REPLIT_DB_URL"))

intents = discord.Intents.all()
intents.members = True
bot = commands.Bot(command_prefix="!", intents=intents)

# ===== Weryfikacja =====
class VerificationModal(Modal, title="Weryfikacja"):
    def __init__(self, answer: int, role_id: int):
        super().__init__(timeout=None)
        self.answer = answer
        self.role_id = role_id
        self.add_item(TextInput(label=f"Ile to {random.randint(1, 10)} + {self.answer - random.randint(1, 10)}?", placeholder="Wpisz poprawny wynik", required=True))

    async def on_submit(self, interaction: discord.Interaction):
        try:
            result = int(self.children[0].value)
            if result == self.answer:
                member = interaction.user
                verified_role = interaction.guild.get_role(self.role_id)
                unverified_role_id = db.get("unverified_role")
                unverified_role = interaction.guild.get_role(unverified_role_id)
                
                if verified_role and unverified_role:
                    if unverified_role in member.roles:
                        await member.remove_roles(unverified_role)
                    await member.add_roles(verified_role)
                    await interaction.response.send_message("✅ Weryfikacja zakończona pomyślnie!", ephemeral=True)
                else:
                    await interaction.response.send_message("❌ Wystąpił problem z rolami. Skontaktuj się z administratorem.", ephemeral=True)
            else:
                await interaction.response.send_message("❌ Niepoprawny wynik. Spróbuj ponownie.", ephemeral=True)
        except ValueError:
            await interaction.response.send_message("❌ Wprowadzono niepoprawny format danych.", ephemeral=True)

class VerificationView(View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="Zweryfikuj", style=discord.ButtonStyle.green, custom_id="verify_button")
    async def verify(self, interaction: discord.Interaction, button: Button):
        verified_role_id = db.get("verified_role")
        if verified_role_id and interaction.guild.get_role(verified_role_id) in interaction.user.roles:
            return await interaction.response.send_message("✅ Jesteś już zweryfikowany!", ephemeral=True)
        
        answer = random.randint(10, 50)
        await interaction.response.send_modal(VerificationModal(answer=answer, role_id=verified_role_id))

# ===== Komendy do weryfikacji =====
@bot.tree.command(name="ustaw_weryfikacje", description="Ustaw panel weryfikacji w wybranym kanale.")
@commands.has_permissions(administrator=True)
async def ustaw_weryfikacje(interaction: discord.Interaction, kanal: discord.TextChannel, rola: discord.Role):
    db.set("verification_channel", kanal.id)
    db.set("verified_role", rola.id)
    
    unverified_role_id = db.get("unverified_role")
    if unverified_role_id:
        unverified_role = interaction.guild.get_role(unverified_role_id)
        if unverified_role:
            await kanal.set_permissions(unverified_role, read_messages=True, send_messages=True)
            await kanal.set_permissions(interaction.guild.default_role, read_messages=False)
            await kanal.set_permissions(rola, read_messages=False)
            
    embed = discord.Embed(
        title="🤖 Weryfikacja",
        description="Aby uzyskać dostęp do serwera, zweryfikuj się, klikając przycisk poniżej.",
        color=discord.Color.blue()
    )
    await kanal.send(embed=embed, view=VerificationView())
    await interaction.response.send_message(f"✅ Panel weryfikacji ustawiony w kanale {kanal.mention} z rolą {rola.mention}.", ephemeral=True)

@bot.tree.command(name="stworz_role", description="Tworzy dwie role do weryfikacji.")
@commands.has_permissions(administrator=True)
async def stworz_role(interaction: discord.Interaction):
    try:
        unverified_role = await interaction.guild.create_role(name="Brak weryfikacji")
        verified_role = await interaction.guild.create_role(name="Po weryfikacji")
        
        for channel in interaction.guild.channels:
            await channel.set_permissions(unverified_role, read_messages=False)
        
        db.set("unverified_role", unverified_role.id)
        db.set("verified_role", verified_role.id)
        await interaction.response.send_message(f"✅ Utworzono role: {unverified_role.mention} i {verified_role.mention}.", ephemeral=True)
    except discord.Forbidden:
        await interaction.response.send_message("❌ Nie mam uprawnień do tworzenia ról!", ephemeral=True)

# ===== Formularz (Modal) do zmiany nazwy ticketa =====
class RenameModal(Modal, title="Zmień nazwę ticketa"):
    new_name = TextInput(label="Nowa nazwa kanału", placeholder="np. ticket-nowa-nazwa", required=True)

    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        await interaction.channel.edit(name=self.new_name.value)
        await interaction.followup.send(f"✅ Nazwa ticketa zmieniona na: **{self.new_name.value}**", ephemeral=True)

# ===== Kontrolki Ticketa =====
class TicketControls(View):
    def __init__(self, bot_instance):
        super().__init__(timeout=None)
        self.claimed_by = None
        self.bot_instance = bot_instance

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
        
        ping_role_id = db.get("ticket_ping_role")
        if ping_role_id:
            ping_role = interaction.guild.get_role(int(ping_role_id))
            if ping_role not in interaction.user.roles and not interaction.user.guild_permissions.manage_channels:
                return await interaction.response.send_message("❌ Nie masz uprawnień, aby odebrać ten ticket.", ephemeral=True)
        
        self.claimed_by = interaction.user.id
        await interaction.response.send_message(f"✅ Ticket odebrany przez {interaction.user.mention}", ephemeral=False)
        button.disabled = True
        await interaction.message.edit(view=self)
        
# ===== Formularz (Modal) do tworzenia ticketa =====
class TicketModal(Modal, title="Formularz Ticketa"):
    nick = TextInput(label="Twój nick w Minecraft", placeholder="np. Kowalski123", required=True)

    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        guild = interaction.guild

        overwrites = {
            guild.default_role: discord.PermissionOverwrite(read_messages=False),
            interaction.user: discord.PermissionOverwrite(read_messages=True, send_messages=True),
            guild.me: discord.PermissionOverwrite(read_messages=True, send_messages=True)
        }
        
        ping_role_id = db.get("ticket_ping_role")
        if ping_role_id:
            ping_role = guild.get_role(int(ping_role_id))
            if ping_role:
                overwrites[ping_role] = discord.PermissionOverwrite(read_messages=True, send_messages=True)
        
        try:
            channel = await guild.create_text_channel(
                name=f"ticket-{interaction.user.name}".lower().replace(" ", "-"),
                overwrites=overwrites
            )
        except discord.Forbidden:
            return await interaction.followup.send("❌ Bot nie ma uprawnień do tworzenia kanałów!", ephemeral=True)

        mention_text = ping_role.mention if ping_role_id else "Nowy ticket!"

        embed = discord.Embed(title="🎟️ Ticket", color=discord.Color.green())
        embed.add_field(name="👤 Użytkownik", value=interaction.user.mention, inline=True)
        embed.add_field(name="🎮 Nick w Minecraft", value=self.nick.value, inline=False)
        embed.set_footer(text=f"ID Użytkownika: {interaction.user.id}")

        view = TicketControls(bot)
        await channel.send(f"{mention_text}", embed=embed, view=view)
        await interaction.followup.send(f"✅ Ticket utworzony: {channel.mention}", ephemeral=True)

# ===== Panel kategorii (2 testowe) =====
class CategorySelect(View):
    def __init__(self, bot_instance):
        super().__init__(timeout=None)
        self.bot_instance = bot_instance
    
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

# ===== Komendy dla ticketów =====
@bot.tree.command(name="setup_tickets", description="Wyślij panel ticketów")
@commands.has_permissions(administrator=True)
async def setup_tickets(interaction: discord.Interaction):
    embed = discord.Embed(
        title="🎟️ Centrum Pomocy",
        description="Wybierz kategorię, aby utworzyć ticket.",
        color=discord.Color.blue()
    )
    await interaction.channel.send(embed=embed, view=CategorySelect(bot))
    await interaction.response.send_message("✅ Panel ticketów wysłany!", ephemeral=True)

@bot.tree.command(name="ustaw_role_ping", description="Ustaw rolę do pingowania przy nowym tickecie i będzie miała do nich dostęp.")
@commands.has_permissions(administrator=True)
async def ustaw_role_ping(interaction: discord.Interaction, rola: discord.Role):
    db.set("ticket_ping_role", rola.id)
    await interaction.response.send_message(f"✅ Rola do pingowania ustawiona na {rola.mention}", ephemeral=True)

@bot.tree.command(name="zamknij", description="Zamyka obecny ticket.")
async def close_command(interaction: discord.Interaction):
    if not interaction.channel.name.startswith("ticket-"):
        return await interaction.response.send_message("❌ To nie jest kanał z ticketem.", ephemeral=True)
    await interaction.response.send_message("Ticket zostanie zamknięty za 5s...", ephemeral=True)
    await asyncio.sleep(5)
    await interaction.channel.delete()

@bot.tree.command(name="zmien_nazwe", description="Zmienia nazwę kanału ticketu.")
async def rename_command(interaction: discord.Interaction):
    if not interaction.user.guild_permissions.manage_channels:
        return await interaction.response.send_message("❌ Nie masz uprawnień do zmiany nazwy.", ephemeral=True)
    await interaction.response.send_modal(RenameModal())

@bot.tree.command(name="unclaim", description="Anuluje odebranie ticketa przez sprzedawcę.")
async def unclaim_command(interaction: discord.Interaction):
    if not interaction.channel.name.startswith("ticket-"):
        return await interaction.response.send_message("❌ To nie jest kanał z ticketem.", ephemeral=True)
    
    ping_role_id = db.get("ticket_ping_role")
    if ping_role_id:
        ping_role = interaction.guild.get_role(int(ping_role_id))
        if ping_role:
            await interaction.channel.set_permissions(ping_role, overwrite=None)
    
    await interaction.response.send_message("✅ Ticket został anulowany. Można go odebrać ponownie.", ephemeral=False)
    message = await interaction.channel.fetch_message(interaction.channel.last_message_id)
    view = TicketControls(bot)
    await message.edit(view=view)

# ===== Dodatkowe funkcje i events =====
@bot.event
async def on_ready():
    bot.add_view(CategorySelect(bot))
    bot.add_view(TicketControls(bot))
    bot.add_view(VerificationView())
    print(f"✅ Zalogowano jako {bot.user}")
    await bot.tree.sync()

if TOKEN:
    bot.run(TOKEN)
else:
    print("❌ Brak tokena w Secrets!")
