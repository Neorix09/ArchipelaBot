# TODO New Interface instead of the Client
# TODO Re.compile HaT Neorix (Team #1) has changed tags from ['AP'] to ['DeathLink'].

# TODO Discord Modus with Pings
# TODO Send all Hints 

from __future__ import annotations
import Utils
import asyncio
from copy import deepcopy
import logging
from NetUtils import JSONtoTextParser, JSONMessagePart
import os
import gettext
import re
import urllib.request
import urllib.error
import urllib.parse

from CommonClient import CommonContext, server_loop, \
    gui_enabled, ClientCommandProcessor, logger, get_base_parser

import discord
from discord.ext import commands
from discord import app_commands

# --- Language ---
try:
    # Try to get the locale directory from the module's location
    localedir = os.path.join(os.path.abspath(os.path.dirname(__file__)), 'locale')
    if not os.path.exists(localedir):
        localedir = os.path.join(os.path.abspath(os.getcwd()), 'worlds', 'archipelabot', 'locale')
    t = gettext.translation('messages', localedir=localedir, fallback=True)
except Exception as e:
    logger.warning(f"Failed to load locale files: {e}")
    t = gettext.translation('messages', localedir='', fallback=True)
_ = t.gettext

# --- Variables ---
run_form_source = False
gui_enabled = True
Bot_token = ""
Admin_role_id = None
ap_admins = True
decimal_places_percent = 2

Server_output = ""
Server_Address = ""
SlotName = ""
Password = ""
Admin_Password = ""
Current_User = None
Curren_Player = ""

# --- Persistent Storage ---
storage = Utils.persistent_load()

# -- Client Data --
client_data = storage.get("client", {})
last_server_address = client_data.get("last_server_address", "")

# -- Bot Data --
bot_data = storage.get("bot", {})
Channel_ID = bot_data.get("channel_id", None)
Current_Website = bot_data.get("current_website", "")
last_slot = bot_data.get("last_slot", "")
last_language = bot_data.get("language", "")

Admin_Users = []
if "bot" in storage:
    if "admin_users" in storage["bot"]: 
        Admin_Users.extend(storage["bot"]["admin_users"])
    if "Bot_Token" in storage["bot"]:
        Bot_token = bot_data.get("bot_token", "")
    if "admin_id" in storage["bot"]:
        Admin_role_id = bot_data.get("admin_id", None)
    if "bot_token" in storage["bot"]:
        Bot_token = bot_data.get("bot_token", "")
    if "channel_id" in storage["bot"]:
        Channel_ID = bot_data.get("channel_id", None)

def set_language(language: str):
    global last_language, _
    Utils.persistent_store("bot", "language", language)
    last_language = language
    try:
        lang = gettext.translation('messages', localedir=localedir, languages=[language], fallback=True)
        lang.install()
        _ = lang.gettext
    except Exception as e:
        logger.warning(f"Failed to set language '{language}': {e}")
        _ = lambda s: s

if last_language:
    set_language(last_language)

class MyBot(commands.Bot):
    def __init__(self):
        intents = discord.Intents.default()
        intents.message_content = True
        super().__init__(command_prefix='>', intents=intents)

    async def setup_hook(self):
        await self.add_cog(DiscordCommands(self))
        await self.tree.sync()
        logger.info(_("Slash commands for {user} synchronized!").format(user=self.user))
        logger.info(_("Bot is ready!"))

    async def set_rich_presence(
        self,
        text: str,
        *,
        details: str | None = None,
        state: str | None = None,
        status: discord.Status = discord.Status.online,
    ):
        activity_kwargs: dict[str, object] = {
            "type": discord.ActivityType.playing,
            "name": text[:128],
        }
        if details:
            activity_kwargs["details"] = details[:128]
        if state:
            activity_kwargs["state"] = state[:128]
        activity = discord.Activity(**activity_kwargs)
        await self.change_presence(status=status, activity=activity)
bot = MyBot()

class BotJSONToTextParser(JSONtoTextParser):
    def _handle_color(self, node: JSONMessagePart):
        return self._handle_text(node)  # No colors for Discord
    
class DiscordBot(ClientCommandProcessor):
    def __init__(self, ctx):
        super().__init__(ctx)

    def _cmd_start_bot(self) -> bool:
        """Start the Discord bot"""
        if Bot_token:
            asyncio.create_task(bot.start(Bot_token))
        else:
            self.output(_("Missing Bot token"))

    def _cmd_set_token(self, token: str = "") -> bool:
        """Sets the bot token"""
        if token:
            global Bot_token
            Utils.persistent_store("bot", "bot_token", token)
            Bot_token = token
            self.output(_("The token is now stored in the “_persistent_storage.yaml” file. Never share this file with anyone else.\n\nNext time, you won't need to run the command again. You can simply use the /start_bot command"))
        else:
            self.output(_("Please specify the token."))
    
    def _cmd_set_admin(self, admin_id: int = "") -> bool:
        """Sets the admin role"""
        try:
            admin_id = int(admin_id)
        except ValueError:
            self.output(_("The ID must contain only numbers "))
            return
        if admin_id:
            global Admin_role_id
            Utils.persistent_store("bot", "admin_id", admin_id)
            Admin_role_id = admin_id
            self.output(_("The admin ID has been updated"))
        else:
            self.output(_("The admin ID could not be updated"))
    
    def _cmd_clear_admin(self) -> bool:
        """Clears the admin role"""
        Utils.persistent_store("bot", "admin_id", None)
        self.output(_("The admin ID has been deleted.\nEveryone on the server can now use admin commands."))

class DiscordBotContext(CommonContext):
    tags = {'TextOnly', 'DeathLink'}
    command_processor = DiscordBot
    items_handling = 7

    def __init__(self, server_address, password):
        super().__init__(server_address, password)
        self.game = ""
        self.jsontotext = BotJSONToTextParser(self)
        self.pending_message: discord.Message = None
        # Admin Command
        self.last_admin_command = None
        # Hint 
        self.last_hint_item = None
        self.last_hint_name = None
        self.last_hint_location = None
        self.last_hint_command = None
        self.hint_wrong = None
        self.hint_suggestion = None

    async def server_auth(self, password_requested: bool = False):
        if password_requested and not self.password:
            await super().server_auth(password_requested)
        await self.get_username()
        await self.send_connect()

    def run_gui(self):
        from kvui import GameManager

        class BotManager(GameManager):
            base_title = "ArchipelaBot Client"

        self.ui = BotManager(self)
        self.ui_task = asyncio.create_task(self.ui.async_run(), name="UI")

    def handle_connection_loss(self, msg: str) -> None:
        super().handle_connection_loss(msg)
        asyncio.create_task(
            bot.set_rich_presence(
                _("Not connected"),
                status=discord.Status.idle
            )
        )
        # Fehler an Discord senden
        embed = discord.Embed(
            title=_("❌ Connection error"),
            description=msg,
            color=discord.Color.red()
        )
        if self.pending_message:
            asyncio.create_task(self.pending_message.edit(embed=embed))
            self.pending_message = None
        else:
            asyncio.create_task(bot.get_cog('DiscordCommands').send_embed(Channel_ID, embed))

    def on_package(self, cmd: str, args: dict):
        if cmd == "Connected":
            logger.info(f"Successfully connected! Slot-Number: {self.slot}")
            total_players = len(args.get("slot_info", {}))
            asyncio.create_task(
                bot.set_rich_presence(
                    _("Archipelago Session"),
                    details=_("Slot: {username}").format(username=self.username),
                    state=_("Player: {total_players} | {server_address}").format(total_players=total_players, server_address=self.server_address),
                    status=discord.Status.online
                )
            )
            # Erfolgreiche Verbindung an Discord melden
            embed = discord.Embed(
                title=_("✅ Connected"),
                description=_("Successfully connected to the server!\nSlot: `{username}`").format(username=self.username),
                color=discord.Color.green()
            )
            if self.pending_message:
                asyncio.create_task(self.pending_message.edit(embed=embed))
                self.pending_message = None
            else:
                asyncio.create_task(bot.get_cog('DiscordCommands').send_embed(Channel_ID, embed))

    def format_progress_bar(self, current: int, total: int, length: int = 20) -> str:
        if total <= 0:
            return _("[No data]")
        filled = int((current / total) * length)
        filled = max(0, min(filled, length))
        return "▰" * filled + "▱" * (length - filled)

    def on_print_json(self, args: dict):
        server_text = self.jsontotext(deepcopy(args["data"]))
        super().on_print_json(args)

        if not server_text or ": !admin" in server_text:
            return

        # Player Status-Ausgabe
        if "Player Status on" in server_text or "connections" in server_text:
            lines = [l.strip() for l in server_text.splitlines() if l.strip()]
            pattern = re.compile(r"^(?P<player>.+?) has (?P<connections>\d+) connection[s]?" \
                                 r"(?: and has finished)?\. \((?P<done>\d+)/(?: )?(?P<total>\d+)\)")
            status_rows = []

            for line in lines:
                m = pattern.search(line)
                if m:
                    player = m.group("player")
                    connections = int(m.group("connections"))
                    done = int(m.group("done"))
                    total = int(m.group("total"))
                    is_finished = "has finished" in line
                    status_rows.append((player, connections, done, total, is_finished))

            if status_rows:
                title = _("Player status")
                desc_parts = []
                overall_color = discord.Color.orange()
                all_done = True
                done_all = 0
                total_all = 0

                for player, connections, done, total, finished in status_rows:
                    if not finished:
                        all_done = False
                    status_text = _("✅ Finished") if finished else _("⏳ In progress")
                    bar = self.format_progress_bar(done, total)
                    percent = round((done / total) * 100, decimal_places_percent)
                    desc_parts.append(_("**{player}** | Connections: {connections} | {status_text}\n{bar} {done}/{total} {percent}%").format(
                        player=player, connections=connections, status_text=status_text, bar=bar, done=done, total=total, percent=percent))
                    
                    done_all = done_all + done
                    total_all = total_all + total
                bar_all = self.format_progress_bar(done_all, total_all)
                percent_all = percent = round((done_all / total_all) * 100, 2)
                desc_parts.append(_("\n**Total:**\n{bar_all} {done_all}/{total_all} {percent_all}%").format(
                    bar_all=bar_all, done_all=done_all, total_all=total_all, percent_all=percent_all))

                if all_done:
                    overall_color = discord.Color.green()

                embed = discord.Embed(
                    title=title,
                    description="\n\n".join(desc_parts),
                    color=overall_color
                )
                if self.pending_message:
                    asyncio.create_task(self.pending_message.edit(embed=embed))
                    self.pending_message = None
                else:
                    asyncio.create_task(bot.get_cog('DiscordCommands').send_embed(Channel_ID, embed))
                return
        
        # Generische Ausgabe
        # Hints
        if "[Hint]" in server_text:

            embed_color = discord.Color.gold()
            embed_titel = _("Hint")
            pattern = re.compile(r"^\[Hint\]: (?P<item_player>.+?)'s (?P<item>.+?) is at (?P<location>.+?) in (?P<location_player>.+?)'s World.*? \((?P<status>.+?)\)")
            m = pattern.search(server_text)

            if m:
                item_player = m.group("item_player")
                item = m.group("item")
                location = m.group("location")
                location_player = m.group("location_player")
                status = m.group("status")

                if status == "found":
                    embed_titel = _("Item already found")
                    embed_color = discord.Color.green()
                    server_text = _("The item **{item}** for {item_player} was already found by {location_player} at **{location}**").format(
                        item=item, item_player=item_player, location_player=location_player, location=location)
                else:
                    server_text = _("**{item}** for {item_player} is at **{location}** in **{location_player}**'s world").format(
                        item=item, item_player=item_player, location=location, location_player=location_player)

            embed = discord.Embed(
                title=embed_titel,
                description=server_text, 
                color=embed_color
            )
            if self.pending_message:
                asyncio.create_task(self.pending_message.edit(embed=embed))
                self.pending_message = None
            else:
                asyncio.create_task(bot.get_cog('DiscordCommands').send_embed(Channel_ID, embed))
            return
        elif "did you mean" in server_text.lower() or "closely matches" in server_text:
            embed_color = discord.Color.gold()
            
            wrong = None
            suggestion = None
            
            m1 = re.search(r"Didn't find something that closely matches '(?P<wrong>.+?)', did you mean '(?P<suggestion>.+?)'\??", server_text)
            m2 = re.search(r"Too many close matches for '(?P<wrong>.+?)', did you mean '(?P<suggestion>.+?)'\??", server_text)
            
            if m1:
                wrong = m1.group("wrong")
                suggestion = m1.group("suggestion")
                self.hint_wrong = wrong
                self.hint_suggestion = suggestion
                description = _("The server could not uniquely identify **{wrong}**. Did you mean **{suggestion}**?").format(wrong=wrong, suggestion=suggestion)
            elif m2:
                wrong = m2.group("wrong")
                suggestion = m2.group("suggestion")
                self.hint_wrong = wrong
                self.hint_suggestion = suggestion
                description = _("The server could not uniquely identify **{wrong}**. Did you mean **{suggestion}**?").format(wrong=wrong, suggestion=suggestion)
            else:
                description = server_text

            embed = discord.Embed(
                title=_("Hint - Not unique"),
                description=description,
                color=embed_color
            )

            if suggestion:
                Hint_suggestions_View = Discord_View.HintsuggestionsView(bot.get_cog('DiscordCommands').ap_ctx)
                if self.pending_message:
                    asyncio.create_task(self.pending_message.edit(embed=embed, view=Hint_suggestions_View))
                    self.pending_message = None
                else:
                    asyncio.create_task(bot.get_cog('DiscordCommands')._send_embed_now(Channel_ID, embed, view=Hint_suggestions_View))
            else:
                if self.pending_message:
                    asyncio.create_task(self.pending_message.edit(embed=embed))
                    self.pending_message = None
                else:
                    asyncio.create_task(bot.get_cog('DiscordCommands').send_embed(Channel_ID, embed))
            return
        elif "No hints found" in server_text:
            embed_color = discord.Color.red()
            embed = discord.Embed(title=_("No hint"), description=_("The requested item does not exist"), color=embed_color)
            if self.pending_message:
                asyncio.create_task(self.pending_message.edit(embed=embed))
                self.pending_message = None
            else:
                asyncio.create_task(bot.get_cog('DiscordCommands').send_embed(Channel_ID, embed))
            return
        # Admin Password
        elif "You must first login using !admin login [password]" in server_text:
            embed_color = discord.Color.red()
            embed = discord.Embed(title=_("Admin login required"), description=_("You must first login as admin using `!admin login [password]` to use this command."), color=embed_color)
            login_view = Discord_View.AdminLoginView(bot.get_cog('DiscordCommands').ap_ctx)
            if self.pending_message:
                asyncio.create_task(self.pending_message.edit(embed=embed, view=login_view))
                self.pending_message = None
                return
            else:
                asyncio.create_task(bot.get_cog('DiscordCommands')._send_embed_now(Channel_ID, embed, view=login_view))
                return
        elif "Login successful. You can now issue server side commands." in server_text:
            send_view = Discord_View.AdminCommandSendView(bot.get_cog('DiscordCommands').ap_ctx)
            embed_color = discord.Color.green()
            embed = discord.Embed(title=_("Login successful"), description=_("You can now use admin commands"), color=embed_color)
            if Current_User not in Admin_Users:
                Admin_Users.append(Current_User)
                Utils.persistent_store("bot", "admin_users", Admin_Users)
                embed.description = _("You are now logged in as admin and added to the list.")
            else:
                embed.description = _("You are now logged in as admin.")
            if self.pending_message:
                if self.last_admin_command:
                    asyncio.create_task(self.pending_message.edit(embed=embed, view=send_view))
                else:
                    asyncio.create_task(self.pending_message.edit(embed=embed))
                self.pending_message = None
                return
            else:
                if self.last_admin_command:
                    asyncio.create_task(bot.get_cog('DiscordCommands').send_embed(Channel_ID, embed, view=send_view))
                else:
                    asyncio.create_task(bot.get_cog('DiscordCommands').send_embed(Channel_ID, embed))
                return
        elif "Password incorrect" in server_text:
            embed_color = discord.Color.red()
            if Current_User in Admin_Users:
                embed = discord.Embed(title=_("Login failed"), description=_("Incorrect password. The bot was not logged in as admin."), color=embed_color)
            else:
                embed = discord.Embed(title=_("Login failed"), description=_("Incorrect password. You were not added to the admin list."), color=embed_color)
            login_view = Discord_View.AdminLoginView(bot.get_cog('DiscordCommands').ap_ctx)
            if self.pending_message:
                asyncio.create_task(self.pending_message.edit(embed=embed, view=login_view))
                self.pending_message = None
                return
            else:
                asyncio.create_task(bot.get_cog('DiscordCommands')._send_embed_now(Channel_ID, embed, view=login_view))
                return
        # Item Send
        elif "found their" in server_text:
            embed_color = discord.Color.blue()
            pattern = re.compile(r"^(?P<sender>.+?) found their (?P<item>.+) \((?P<location>.+)\)$")
            m = pattern.search(server_text)
            
            if m:
                sender = m.group("sender")
                item = m.group("item")
                location = m.group("location")

                server_text = _("**{sender}** found their **{item}** \n> {location}").format(sender=sender, item=item, location=location)
        elif "sent" in server_text:
            embed_color = discord.Color.blue()
            pattern = re.compile(r"^(?P<sender>.+?) sent (?P<item>.+?) to (?P<recipient>.+?) \((?P<location>.+)\)$")
            m = pattern.search(server_text)
            
            if m:
                sender = m.group("sender")
                item = m.group("item")
                recipient = m.group("recipient")
                location = m.group("location")

                server_text = _("**{sender}** sent **{item}** to **{recipient}** \n> {location}").format(sender=sender, item=item, recipient=recipient, location=location)
        # Other Events
        elif "has joined" in server_text:
            embed_color = discord.Color.green()
            pattern = re.compile(r"^(?P<player>.+?) \(.*?\) (?P<client_type>\S+) (?P<game>.+?) has joined\. Client\(.*?\), \[(?P<tag>[^\]]*)\]\.$")
            m = pattern.search(server_text)
            if m:
                new_player = m.group("player")
                client_type = m.group("client_type")
                game = m.group("game")
                tag = m.group("tag")
                tag_list = [t.strip().replace("'", "") for t in tag.split(",")]

                if tag_list[0] == "":
                    tag_label = _("No Tags")
                else:
                    tag_label = _("Tag:") if len(tag_list) == 1 else _("Tags:")
                formatted_tags = ", ".join(tag_list)

                if client_type == "hinting":
                    embed = discord.Embed(
                        title=_("Hintgame connected"),
                        description=_("**{new_player}** has joined the server and is playing a hintgame for **{game}**\n> {tag_label} {formatted_tags}").format(
                            new_player=new_player, game=game, tag_label=tag_label, formatted_tags=formatted_tags),
                        color=embed_color
                    ) 
                elif client_type == "tracking":
                    embed = discord.Embed(
                        title=_("Tracker connected"),
                        description=_("**{new_player}** has joined the server and is tracking **{game}**\n> {tag_label} {formatted_tags}").format(
                            new_player=new_player, game=game, tag_label=tag_label, formatted_tags=formatted_tags),
                        color=embed_color
                    )
                elif client_type == "viewing":
                    embed = discord.Embed(
                        title=_("Text Client connected"),
                        description=_("**{new_player}** has joined the server and is watching **{game}**\n> {tag_label} {formatted_tags}").format(
                            new_player=new_player, game=game, tag_label=tag_label, formatted_tags=formatted_tags),
                        color=embed_color
                    )
                else:
                    embed = discord.Embed(
                        title=_("{new_player} connected").format(new_player=new_player),
                        description=_("**{new_player}** has joined the server and is playing **{game}**\n> {tag_label} {formatted_tags}").format(
                            new_player=new_player, game=game, tag_label=tag_label, formatted_tags=formatted_tags),
                        color=embed_color
                    )
                asyncio.create_task(bot.get_cog('DiscordCommands')._send_embed_now(Channel_ID, embed))
                return
        elif "has left the game" in server_text:
            embed_color = discord.Color.red()
            pattern = re.compile(r"^(?P<player>.+?) \(.*?\) has left the game\. Client\(.*?\), \[(?P<tag>[^\]]*)\]\.$")
            m = pattern.search(server_text)
            if m:
                player = m.group("player")
                tag = m.group("tag")
                tag_list = [t.strip().replace("'", "") for t in tag.split(",")]

                if tag_list[0] == "":
                    tag_label = _("No Tags")
                else:
                    tag_label = _("Tag:") if len(tag_list) == 1 else _("Tags:")
                formatted_tags = ", ".join(tag_list)

                embed = discord.Embed(
                    title=_("{player} disconnected").format(player=player),
                    description=_("**{player}** has left the game.\n> {tag_label} {formatted_tags}").format(
                        player=player, tag_label=tag_label, formatted_tags=formatted_tags),
                    color=embed_color
                )
                asyncio.create_task(bot.get_cog('DiscordCommands')._send_embed_now(Channel_ID, embed))
                return
        elif "players of" in server_text and "connected" in server_text:
            embed_color = discord.Color.orange()

            pattern = re.compile(r"^(?P<players>\d+) players? of (?P<total>\d+) connected :: Team #1: (?P<all_slots>.+)")
            m = pattern.search(server_text)
            if m:
                players = int(m.group("players"))
                total_players = int(m.group("total"))
                all_slots = m.group("all_slots")
                
                # Extrahiere alle Einträge: entweder (Name) oder reiner Text
                entries = re.findall(r'\([^)]+\)|[^()\s]+(?:\s+[^()\s]+)*', all_slots)

                # Trenne in offline (mit Klammern) und online (ohne)
                offline_slots = [entry.strip('()') for entry in entries if entry.startswith('(')]
                online_slots = [entry for entry in entries if not entry.startswith('(')]
                
                online_list = "\n".join('- ' + slot for slot in online_slots)
                offline_list = "\n".join('- ' + slot for slot in offline_slots)
                server_text = _("There are {players}/{total_players} players connected.\n\nOnline:\n{online_list}\n\nOffline:\n{offline_list}").format(
                    players=players, total_players=total_players, online_list=online_list, offline_list=offline_list)

            embed = discord.Embed(
                title=_("Player information"), 
                description=server_text, 
                color=embed_color
            )
            if self.pending_message:
                asyncio.create_task(self.pending_message.edit(embed=embed))
                self.pending_message = None
            else:
                asyncio.create_task(bot.get_cog('DiscordCommands').send_embed(Channel_ID, embed))
            return
        elif "Game saved" in server_text:
            embed_color = discord.Color.green()
            embed = discord.Embed(title=_("Successfully saved"), description=_("The game has been saved."), color=embed_color)
            if self.pending_message:
                asyncio.create_task(self.pending_message.edit(embed=embed))
                self.pending_message = None
            else:
                asyncio.create_task(bot.get_cog('DiscordCommands').send_embed(Channel_ID, embed))
            return
        elif "Now that you are connected" in server_text:
            embed_color=discord.Color.green()
            server_text=_("You are now connected to the server. Use /help to list available commands.")
        else:
            embed_color = discord.Color.blue()

        embed = discord.Embed(description=server_text, color=embed_color)
        asyncio.create_task(bot.get_cog('DiscordCommands').send_embed(Channel_ID, embed))

class AdminLoginModal(discord.ui.Modal, title=_("Admin Login")):
    password = discord.ui.TextInput(
        label=_("Admin Password"),
        style=discord.TextStyle.short,
        placeholder=_("Enter password"),
        required=True,
    )

    def __init__(self, ap_ctx: DiscordBotContext):
        super().__init__()
        self.ap_ctx = ap_ctx

    async def on_submit(self, interaction: discord.Interaction) -> None:
        if not self.ap_ctx or not self.ap_ctx.server_address:
            embed = discord.Embed(
                title=_("❌ Connection error"),
                description=_("The bot is not connected to any server! Please connect to a server first using the `/connect` command."),
                color=discord.Color.red()
            )
            await interaction.response.send_message(_("The bot is not connected to any server!"), ephemeral=True)
            return

        await interaction.response.defer()

        embed = discord.Embed(
            title=_("Admin Login"),
            description=_("The login command has been sent to the server. Waiting for server response..."),
            color=discord.Color.purple()
        )
        message = await interaction.followup.send(embed=embed)
        self.ap_ctx.pending_message = message

        await self.ap_ctx.send_msgs([{"cmd": "Say", "text": f"!admin login {self.password.value}"}])

class Discord_View():    
    class AdminLoginView(discord.ui.View):
        def __init__(self, ap_ctx: DiscordBotContext):
            super().__init__(timeout=300)
            self.ap_ctx = ap_ctx

        @discord.ui.button(label=_("Open Admin Login"), style=discord.ButtonStyle.primary)
        async def open_admin_login(self, interaction: discord.Interaction, button: discord.ui.Button):
            global Current_User
            Current_User = interaction.user.id
            await interaction.response.send_modal(AdminLoginModal(self.ap_ctx))

    class AdminCommandSendView(discord.ui.View):
        def __init__(self, ap_ctx: DiscordBotContext):
            super().__init__(timeout=300)
            self.ap_ctx = ap_ctx
        
        @discord.ui.button(label=_("Resend command"), style=discord.ButtonStyle.primary)
        async def send_command(self, interaction: discord.Interaction, button: discord.ui.Button):
            await interaction.response.defer(ephemeral=True)
            command = self.ap_ctx.last_admin_command
            if command[0] == "hint":
                self.ap_ctx.last_admin_command = None
                await self.ap_ctx.send_msgs([{"cmd": "Say", "text": f"!admin /hint '{command[1]}' '{command[2]}'"}])
            elif command[0] == "hint_location":
                self.ap_ctx.last_admin_command = None
                await self.ap_ctx.send_msgs([{"cmd": "Say", "text": f"!admin /hint_location '{command[1]}' '{command[2]}'"}])
            else:
                embed = discord.Embed(
                    title=_("Unknown command"),
                    description=_("No command could be sent."),
                    color=discord.Color.red()
                )
                asyncio.create_task(bot.get_cog('DiscordCommands')._send_embed_now(Channel_ID, embed))

    class HintsuggestionsView(discord.ui.View):
        def __init__(self, ap_ctx: DiscordBotContext):
            super().__init__(timeout=300)
            self.ap_ctx = ap_ctx
            
            if self.ap_ctx.hint_wrong == self.ap_ctx.last_hint_name:
                self.category = "name"
            elif self.ap_ctx.hint_wrong == self.ap_ctx.last_hint_item:
                self.category = "item"
            else:
                self.category = "location"

            btn = discord.ui.Button(
                label=_("Ask again (Correction {category}: {suggestion})").format(category=self.category, suggestion=self.ap_ctx.hint_suggestion),
                style=discord.ButtonStyle.primary
            )
            
            btn.callback = self.send_hint
            self.add_item(btn)

        async def send_hint(self, interaction: discord.Interaction):
            await interaction.response.defer(ephemeral=True)
            
            suggestion = self.ap_ctx.hint_suggestion
            name = self.ap_ctx.last_hint_name
            item = self.ap_ctx.last_hint_item
            location = self.ap_ctx.last_hint_location
            is_admin = getattr(self.ap_ctx, 'last_hint_is_admin', False)

            msg_text = ""
            if self.category == "name":
                self.ap_ctx.last_hint_name = suggestion
                if self.ap_ctx.last_hint_command == "item":
                    if is_admin:
                        msg_text = f"!admin /hint '{suggestion}' '{item}'"
                    else:
                        msg_text = f"!hint {item}"
                else:
                    if is_admin:
                        msg_text = f"!admin /hint_location '{suggestion}' '{location}'"
                    else:
                        msg_text = f"!hint_location {location}"
            elif self.category == "item":
                self.ap_ctx.last_hint_item = suggestion
                if is_admin:
                    msg_text = f"!admin /hint '{name}' '{suggestion}'"
                else:
                    msg_text = f"!hint {suggestion}"
            else:
                self.ap_ctx.last_hint_location = suggestion
                if is_admin:
                    msg_text = f"!admin /hint_location '{name}' '{suggestion}'"
                else:
                    msg_text = f"!hint_location {suggestion}"
            
            if msg_text:
                await self.ap_ctx.send_msgs([{"cmd": "Say", "text": msg_text}])
            else:
                await interaction.followup.send(_("Error: Could not generate command."), ephemeral=True)
            return

    class SendlastaddressView(discord.ui.View):
        def __init__(self, cog: DiscordCommands):
            super().__init__(timeout=300)
            self.cog = cog

        @discord.ui.button(label=_("Use last address"), style=discord.ButtonStyle.primary)
        async def setaddress(self, interaction: discord.Interaction, button: discord.ui.Button):
            await interaction.response.defer(ephemeral=True)
            global Server_Address, Password, SlotName
            Server_Address = last_server_address

            if not self.cog.ap_ctx:
                self.cog.ap_ctx = DiscordBotContext(Server_Address, Password)

            self.cog.ap_ctx.server_address = Server_Address
            self.cog.ap_ctx.password = Password
            self.cog.ap_ctx.username = SlotName

            asyncio.create_task(self.cog.ap_ctx.connect())

class get_webinfo():
    def _normalize_url(url: str) -> str:

        url = url.strip()
        if not url:
            return url
        if not re.match(r"^https?://", url, re.I):
            url = "https://" + url
        return url

    def _trigger_url(url: str, timeout: int = 15) -> tuple[bool, str]:
        req = urllib.request.Request(
            url,
            headers={"User-Agent": "ArchipelaBot/1.0"},
            method="GET",
        )
        try:
            with urllib.request.urlopen(req, timeout=timeout) as response:
                status = response.getcode()
                return 200 <= status < 400, f"HTTP {status}"
        except urllib.error.HTTPError as exc:
            return False, f"HTTP {exc.code}"
        except Exception as exc:
            return False, str(exc)

    def _extract_server_address_from_html(html: str) -> tuple[str, int] | None:
        tooltip_match = re.search(
            r'data-tooltip="([^"]*address/ip is[^"]*and port is[^"]*)"',
            html,
            re.I,
        )
        if not tooltip_match:
            return None
        tooltip = tooltip_match.group(1)
        match = re.search(
            r"address/ip is\s+([^\s]+)\s+and port is\s+(\d+)",
            tooltip,
            re.I,
        )
        if not match:
            return None
        return match.group(1), int(match.group(2))

    def _fetch_server_address_from_website(url: str, timeout: int = 15) -> tuple[bool, str, str | None]:
        req = urllib.request.Request(
            url,
            headers={"User-Agent": "ArchipelaBot/1.0"},
            method="GET",
        )
        try:
            with urllib.request.urlopen(req, timeout=timeout) as response:
                html = response.read().decode("utf-8", errors="ignore")
            parsed = get_webinfo._extract_server_address_from_html(html)
            if not parsed:
                return False, _("Tooltip with address/ip and port not found."), None
            host, port = parsed
            return True, _("Address recognized: {host}:{port}").format(host=host, port=port), f"{host}:{port}"
        except urllib.error.HTTPError as exc:
            return False, _("HTTP {code} while loading the website.").format(code=exc.code), None
        except Exception as exc:
            return False, str(exc), None

    def _extract_table_entries_from_html(html: str) -> list[dict[str, str]]:
        tables = re.findall(r"<table\b[^>]*>(.*?)</table>", html, flags=re.I | re.S)
        entries: list[dict[str, str]] = []

        for table in tables:
            header_labels: list[str] = []
            rows = re.findall(r"<tr\b[^>]*>(.*?)</tr>", table, flags=re.I | re.S)
            for row in rows:
                headers = re.findall(r"<th\b[^>]*>(.*?)</th>", row, flags=re.I | re.S)
                if headers:
                    header_labels = [
                        re.sub(r"\s+", " ", re.sub(r"<[^>]+>", "", h)).strip().lower()
                        for h in headers
                    ]
                    continue

                cells = re.findall(r"<td\b[^>]*>(.*?)</td>", row, flags=re.I | re.S)
                if not cells:
                    continue

                cell_texts: list[str] = []
                row_cell_links: list[list[tuple[str, str]]] = []
                row_links: list[tuple[str, str]] = []
                for cell in cells:
                    hrefs = re.findall(r'href="([^"]+)"', cell, flags=re.I)
                    link_texts = re.findall(r"<a\b[^>]*>(.*?)</a>", cell, flags=re.I | re.S)
                    cell_links: list[tuple[str, str]] = []
                    for idx, href in enumerate(hrefs):
                        link_text = ""
                        if idx < len(link_texts):
                            link_text = re.sub(r"<[^>]+>", "", link_texts[idx])
                            link_text = re.sub(r"\s+", " ", link_text).strip()
                        pair = (link_text, href)
                        row_links.append(pair)
                        cell_links.append(pair)
                    row_cell_links.append(cell_links)
                    text = re.sub(r"<[^>]+>", "", cell)
                    text = re.sub(r"\s+", " ", text).strip()
                    cell_texts.append(text)

                if not cell_texts:
                    continue

                # Header-Zeilen überspringen
                lower_row = " ".join(cell_texts).lower()
                if "player" in lower_row and ("game" in lower_row or "slot" in lower_row):
                    continue

                index = ""
                if cell_texts and re.fullmatch(r"\d+", cell_texts[0]):
                    index = cell_texts[0]
                else:
                    index = str(len(entries) + 1)

                name = ""
                for text, href in row_links:
                    if not text:
                        continue
                    if text.lower() in {"download", "tracker", "tracker page"}:
                        continue
                    name = text
                    break
                if not name:
                    for ctext in cell_texts:
                        if not ctext or re.fullmatch(r"\d+", ctext):
                            continue
                        if ctext.lower() in {"download", "tracker", "tracker page"}:
                            continue
                        name = ctext
                        break

                game = ""
                # Häufig ist die Spielspalte die dritte Zelle.
                if len(cell_texts) >= 3 and cell_texts[2]:
                    game = cell_texts[2]
                if not game:
                    for ctext in cell_texts:
                        if not ctext or ctext == name or re.fullmatch(r"\d+", ctext):
                            continue
                        if ctext.lower() in {"download", "tracker", "tracker page"}:
                            continue
                        game = ctext
                        break

                download_link = ""
                tracker_link = ""
                no_download_available = any(
                    "no file to download for this game" in (ctext or "").lower()
                    for ctext in cell_texts
                )
                # 1) Bevorzugt über Header-Spalten
                if header_labels:
                    for idx, label in enumerate(header_labels):
                        if idx >= len(row_cell_links):
                            continue
                        links_in_cell = row_cell_links[idx]
                        if not links_in_cell:
                            continue
                        if (
                            ("download" in label or "dl" == label)
                            and not download_link
                            and not no_download_available
                        ):
                            download_link = links_in_cell[0][1]
                        elif "tracker" in label and not tracker_link:
                            tracker_link = links_in_cell[0][1]

                # 2) Über Linktext/Href-Muster
                for text, href in row_links:
                    t = (text or "").lower()
                    h = (href or "").lower()
                    if not no_download_available and not download_link and (
                        "download" in t
                        or "download" in h
                        or h.endswith(".zip")
                        or h.endswith(".apmc")
                        or h.endswith(".apz5")
                        or "/download" in h
                    ):
                        download_link = href
                        continue
                    if not tracker_link and ("tracker" in t or "tracker" in h):
                        tracker_link = href
                        continue

                # 3) Letzter Fallback: ignoriert mw://-Spielerlinks explizit
                if not no_download_available and not download_link:
                    for text, href in row_links:
                        if not href:
                            continue
                        h = href.lower()
                        if h.startswith("mw://") or h.startswith("mwg://"):
                            continue
                        if href != tracker_link:
                            download_link = href
                            break

                if name:
                    entries.append({
                        "index": index,
                        "name": name,
                        "game": game or "-",
                        "download": download_link,
                        "tracker": tracker_link,
                    })

        return entries

    def _fetch_table_from_website(url: str, timeout: int = 15) -> tuple[bool, str, list[dict[str, str]]]:
        req = urllib.request.Request(
            url,
            headers={"User-Agent": "ArchipelaBot/1.0"},
            method="GET",
        )
        try:
            with urllib.request.urlopen(req, timeout=timeout) as response:
                html = response.read().decode("utf-8", errors="ignore")
            entries = get_webinfo._extract_table_entries_from_html(html)
            if not entries:
                return False, _("No matching table entries found."), []
            return True, _("{count} entries found.").format(count=len(entries)), entries
        except urllib.error.HTTPError as exc:
            return False, _("HTTP {code} while loading the website.").format(code=exc.code), []
        except Exception as exc:
            return False, str(exc), []

    def _extract_global_tracker_links_from_html(html: str, base_url: str) -> dict[str, str]:
        result = {"multiworld_tracker": "", "sphere_tracker": ""}

        mw_match = re.search(
            r'<a\b[^>]*href="([^"]+/tracker/[^"]+|/tracker/[^"]+)"[^>]*>\s*Multiworld\s+Tracker\s*</a>',
            html,
            flags=re.I | re.S,
        )
        if mw_match:
            result["multiworld_tracker"] = urllib.parse.urljoin(base_url, mw_match.group(1).strip())

        sphere_match = re.search(
            r'<a\b[^>]*href="([^"]+/sphere_tracker/[^"]+|/sphere_tracker/[^"]+)"[^>]*>\s*Sphere\s+Tracker\s*</a>',
            html,
            flags=re.I | re.S,
        )
        if sphere_match:
            result["sphere_tracker"] = urllib.parse.urljoin(base_url, sphere_match.group(1).strip())

        return result

    def _fetch_global_tracker_links_from_website(url: str, timeout: int = 15) -> tuple[bool, str, dict[str, str]]:
        req = urllib.request.Request(
            url,
            headers={"User-Agent": "ArchipelaBot/1.0"},
            method="GET",
        )
        try:
            with urllib.request.urlopen(req, timeout=timeout) as response:
                html = response.read().decode("utf-8", errors="ignore")
            trackers = get_webinfo._extract_global_tracker_links_from_html(html, url)
            if not trackers["multiworld_tracker"] and not trackers["sphere_tracker"]:
                return False, _("No global tracker links found."), trackers
            return True, _("Global tracker links found."), trackers
        except urllib.error.HTTPError as exc:
            return False, _("HTTP {code} while loading the website.").format(code=exc.code), {"multiworld_tracker": "", "sphere_tracker": ""}
        except Exception as exc:
            return False, str(exc), {"multiworld_tracker": "", "sphere_tracker": ""}

class Discord_suggestions():
    async def ip_suggestions(self, interaction: discord.Interaction, current: str):
        choices = ["archipelago.gg", "multiworld.gg", "localhost"]
        remembered_host = last_server_address.split(":")[0] if last_server_address and ":" in last_server_address else ""

        new_choices = [word for word in choices if word != remembered_host]
        if remembered_host:
            new_choices.insert(0, remembered_host)

        current_l = current.lower()
        return [app_commands.Choice(name=x, value=x) for x in new_choices if current_l in x.lower()]

    async def port_suggestions(self, interaction: discord.Interaction, current: str):
        choices = []
        if last_server_address and ":" in last_server_address:
            choices.append(last_server_address.split(":")[1])
        return [app_commands.Choice(name=x, value=int(x)) for x in choices if x and current in x]

    async def slot_suggestions(self, interaction: discord.Interaction, current: str):
        choices = []
        if last_slot:
            choices.insert(0, last_slot)
        if interaction.user:
            user_name = interaction.user.display_name
            if user_name and user_name != last_slot:
                choices.append(user_name)

        unique_choices = list(dict.fromkeys(choices))
        current_l = current.lower()
        return [app_commands.Choice(name=x, value=x) for x in unique_choices if x and current_l in x.lower()]

    async def language_suggestions(self, interaction: discord.Interaction, current: str):
        choices = [
            app_commands.Choice(name=x,
            value=x
        ) for x in ["English", "Deutsch"]
        ]
        return choices

class DiscordCommands(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.ap_ctx = None
        self._pending_embeds: dict[int, list[discord.Embed]] = {}
        self._flush_tasks: dict[int, asyncio.Task[None]] = {}
        self._flush_delay = 0.2

    @commands.Cog.listener()
    async def on_ready(self):
        await self.bot.set_rich_presence(
            "Archipelago Bot",
            details=_("Waiting for connection"),
            state=_("Use /connect"),
            status=discord.Status.idle
        )

    async def send_embed(self, channel_id: int, embed: discord.Embed):
        pending = self._pending_embeds.setdefault(channel_id, [])
        pending.append(embed)

        task = self._flush_tasks.get(channel_id)
        if task is None or task.done():
            self._flush_tasks[channel_id] = asyncio.create_task(self._flush_embeds(channel_id))

    async def _send_combined_embeds(self, channel_id: int, embeds: list[discord.Embed], default_title: str = ""):
        if not embeds:
            return

        current_parts = []
        current_length = 0
        max_length = 3800 

        for embed in embeds:
            part = ""
            if embed.title:
                if embed.title == "Skip Title":
                    pass
                else:
                    part += f"**{embed.title}**\n"
            if embed.description:
                part += embed.description
            
            part_text = part.strip()
            if not part_text:
                continue

            if len(part_text) > max_length:
                if current_parts:
                    await self._send_embed_now(channel_id, discord.Embed(description="\n\n".join(current_parts), color=embeds[-1].color or discord.Color.blue()))
                    current_parts = []
                    current_length = 0
                
                for i in range(0, len(part_text), max_length):
                    chunk = part_text[i:i+max_length]
                    await self._send_embed_now(channel_id, discord.Embed(description=chunk, color=embeds[-1].color or discord.Color.blue()))
                continue

            if current_length + len(part_text) + 2 > max_length:
                combined_embed = discord.Embed(
                    title=default_title if not current_parts else "", 
                    description="\n\n".join(current_parts), 
                    color=embeds[-1].color or discord.Color.blue()
                )
                await self._send_embed_now(channel_id, combined_embed)
                current_parts = [part_text]
                current_length = len(part_text)
            else:
                current_parts.append(part_text)
                current_length += len(part_text) + 2

        if current_parts:
            combined_embed = discord.Embed(
                title=default_title if len(embeds) == len(current_parts) else "",
                description="\n\n".join(current_parts),
                color=embeds[-1].color or discord.Color.blue()
            )
            await self._send_embed_now(channel_id, combined_embed)

    async def _flush_embeds(self, channel_id: int):
        await asyncio.sleep(self._flush_delay)
        embeds = self._pending_embeds.pop(channel_id, [])
        self._flush_tasks.pop(channel_id, None)

        if not embeds:
            return

        # Hints separat bündeln, andere separat bündeln
        found_hints = []
        other_hints = []
        others = []
        for e in embeds:
            if e.title and (_("Item already found") in e.title):
                e.title = "Skip Title"
                found_hints.append(e)
            elif e.title and (_("Hint") in e.title):
                e.title = "Skip Title"
                other_hints.append(e)
            else:
                others.append(e)

        if found_hints:
            await self._send_combined_embeds(channel_id, found_hints)

        if other_hints:
            await self._send_combined_embeds(channel_id, other_hints)

        if others:
            await self._send_combined_embeds(channel_id, others)

    async def _send_embed_now(self, channel_id: int, embed: discord.Embed, view: discord.ui.View | None = None):
        channel = self.bot.get_channel(channel_id)
        if channel:
            await channel.send(embed=embed, view=view)
        else:
            logger.error(_("Channel with ID {channel_id} not found.").format(channel_id=channel_id))
        
    # -- Set Up Commands --
    @app_commands.command(name="set_server", description=_("Specifies the server address."))
    @app_commands.describe(ip = _("The IP of the server"), port = _("The port of the server"))
    @app_commands.autocomplete(ip=Discord_suggestions.ip_suggestions, port=Discord_suggestions.port_suggestions)
    @commands.has_role(Admin_role_id)
    async def set_server(self, interaction: discord.Interaction, ip: str, port: int):
        global Server_Address
        Server_Address = f"{ip}:{port}"

        embed = discord.Embed(
            title = _("Server updated"),
            description = _("The server address has been set to {ip}:{port}.").format(ip=ip, port=port),
            color = discord.Color.purple()
        )
        await interaction.response.send_message(embed=embed)

    @app_commands.command(name="connect", description=_("Connects to the server."))
    @app_commands.describe(slot = _("The player name"), password = _("The password for the server"))
    @app_commands.autocomplete(slot=Discord_suggestions.slot_suggestions)
    async def connect(self, interaction: discord.Interaction, slot: str, password: str = ""):
        global SlotName, Password, Server_Address
        SlotName = slot
        Password = password
        Utils.persistent_store("bot", "last_slot", SlotName)

        if not Server_Address:
            embed = discord.Embed(
                title = _("Connection error"),
                description = _("No server is set. Please set one via `/set_server`."),
                color = discord.Color.red()
            )
            await interaction.response.send_message(embed=embed, view=Discord_View.SendlastaddressView(self))
            return

        if not self.ap_ctx:
            self.ap_ctx = DiscordBotContext(Server_Address, Password)

        self.ap_ctx.server_address = Server_Address
        self.ap_ctx.password = Password
        self.ap_ctx.username = SlotName

        # Defer interaction to allow follow-up later
        await interaction.response.defer()

        embed = discord.Embed(
            title = _("⏳ Connection attempt in progress..."),
            description = _("A connection to the server `{server_address}` is being established with slot: `{slot_name}`.").format(server_address=Server_Address, slot_name=SlotName),
            color = discord.Color.purple()
        )
        # Nachricht speichern um sie später zu bearbeiten
        message = await interaction.followup.send(embed=embed)
        self.ap_ctx.pending_message = message

        asyncio.create_task(self.ap_ctx.connect())
    
    @commands.has_role(Admin_role_id)
    @app_commands.command(name="disconnect", description=_("Disconnect from the server"))
    async def disconnect(self, interaction: discord.Interaction):
        asyncio.create_task(self.ap_ctx.disconnect(), name="disconnecting")
        
        embed = discord.Embed(
            title=_("Disconnect from Server"),
            description=_("The bot is disconnecting from the server"),
            color=discord.Color.red()
        )
        await interaction.response.send_message(embed=embed)

    # -- Archipelago Commands --
    @app_commands.command(name="admin_login", description=_("Log the bot in as admin"))
    async def admin_login(self, interaction: discord.Interaction):
        # Prüfen, ob der Bot überhaupt verbunden ist
        if not self.ap_ctx or not self.ap_ctx.server_address:
            embed = discord.Embed(
                title=_("❌ Connection error"),
                description=_("The bot is not connected to any server! Please connect to a server first using the `/connect` command."),
                color=discord.Color.red()
            )
            await interaction.response.send_message(embed=embed)
            return
        
        global Current_User
        Current_User = interaction.user.id
        await interaction.response.send_modal(AdminLoginModal(self.ap_ctx))
    
    @app_commands.command(name="save", description=_("Saves the multiworld"))
    async def save(self, interaction: discord.Interaction):
        # Prüfen, ob der Bot überhaupt verbunden ist
        if not self.ap_ctx or not self.ap_ctx.server_address:
            embed = discord.Embed(
                title=_("❌ Connection error"),
                description=_("The bot is not connected to any server! Please connect to a server first using the `/connect` command."),
                color=discord.Color.red()
            )
            await interaction.response.send_message(embed=embed)
            return

        await interaction.response.defer()
        embed = discord.Embed(
            title = _("⏳ Saving..."),
            description = _("The multiworld is being saved. Waiting for server response."),
            color = discord.Color.purple()
        )

        # Nachricht speichern um sie später zu bearbeiten
        message = await interaction.followup.send(embed=embed)
        self.ap_ctx.pending_message = message

        await self.ap_ctx.send_msgs([{"cmd": "Say", "text": f"!admin /save"}])

    @app_commands.command(name="players", description=_("Outputs player information"))
    async def players(self, interaction: discord.Interaction):
        # Prüfen, ob der Bot überhaupt verbunden ist
        if not self.ap_ctx or not self.ap_ctx.server_address:
            embed = discord.Embed(
                title=_("❌ Connection error"),
                description=_("The bot is not connected to any server! Please connect to a server first using the `/connect` command."),
                color=discord.Color.red()
            )
            await interaction.response.send_message(embed=embed)
            return
        
        await interaction.response.defer()
        embed = discord.Embed(
            title = _("⏳ Requesting player info..."),
            description = _("The player info is being requested. Waiting for server response."),
            color = discord.Color.purple()
        )
        # Nachricht speichern um sie später zu bearbeiten
        message = await interaction.followup.send(embed=embed)
        self.ap_ctx.pending_message = message

        await self.ap_ctx.send_msgs([{"cmd": "Say", "text": f"!players"}])

    @app_commands.command(name="status", description=_("Outputs the status of the multiworld"))
    async def status(self, interaction: discord.Interaction):
        if not self.ap_ctx or not self.ap_ctx.server_address:
            embed = discord.Embed(
                title=_("❌ Connection error"),
                description=_("The bot is not connected to any server! Please connect to a server first using the `/connect` command."),
                color=discord.Color.red()
            )
            await interaction.response.send_message(embed=embed)
            return


        await interaction.response.defer()
        embed = discord.Embed(
            title = _("⏳ Status query in progress..."),
            description = _("The status of the multiworld is being requested. Waiting for server response."),
            color = discord.Color.purple()
        )
        
        message = await interaction.followup.send(embed=embed)
        self.ap_ctx.pending_message = message

        await self.ap_ctx.send_msgs([{"cmd": "Say", "text": f"!status"}])

    # -- AP Admin Commnands --
    @app_commands.command(name="hint", description=_("Outputs a hint to the server"))
    @app_commands.describe(player = _("Player the item belongs to"), item=_("The item for which a hint should be given"))
    async def hint(self, interaction: discord.Interaction, player: str, item: str):
        # Prüfen, ob der Bot überhaupt verbunden ist
        if not self.ap_ctx or not self.ap_ctx.server_address:
            embed = discord.Embed(
                title=_("❌ Connection error"),
                description=_("The bot is not connected to any server! Please connect to a server first using the `/connect` command."),
                color=discord.Color.red()
            )
            await interaction.response.send_message(embed=embed)
            return
        
        user_id = interaction.user.id
        self.ap_ctx.last_admin_command = ["hint", player, item]
        if ap_admins:
            if user_id not in Admin_Users:
                embed = discord.Embed(
                    title=_("❌ No permission"),
                    description=_("You do not have permission to use this command. Use `/admin_login` to log in as admin"),
                    color=discord.Color.red()
                )
                await interaction.response.send_message(embed=embed, view=Discord_View.AdminLoginView(self.ap_ctx))
                return

        
        await interaction.response.defer()

        embed = discord.Embed(
            title=_("Hint requested"),
            description=_("A hint for {item} has been requested\nCheck the log for the hint").format(item=item),
            color=discord.Color.purple()
        )

        self.ap_ctx.last_hint_item = item
        self.ap_ctx.last_hint_name = player
        self.ap_ctx.last_hint_command = "item"
        self.ap_ctx.last_hint_is_admin = True
        message = await interaction.followup.send(embed=embed)
        self.ap_ctx.pending_message = message
        await self.ap_ctx.send_msgs([{"cmd": "Say", "text": f"!admin /hint '{player}' '{item}'"}])
    
    @app_commands.command(name="hint_location", description=_("Tells which item is at the location"))
    @app_commands.describe(player = _("Player the item belongs to"), location=_("The item for which a hint should be given"))
    async def hint_location(self, interaction: discord.Interaction, player: str, location: str):
        # Prüfen, ob der Bot überhaupt verbunden ist
        if not self.ap_ctx or not self.ap_ctx.server_address:
            embed = discord.Embed(
                title=_("❌ Connection error"),
                description=_("The bot is not connected to any server! Please connect to a server first using the `/connect` command."),
                color=discord.Color.red()
            )
            await interaction.response.send_message(embed=embed)
            return

        user_id = interaction.user.id
        self.ap_ctx.last_admin_command = ["hint_location", player, location]
        if ap_admins:
            if user_id not in Admin_Users:
                embed = discord.Embed(
                    title=_("❌ No permission"),
                    description=_("You do not have permission to use this command. Use `/admin_login` to log in as admin"),
                    color=discord.Color.red()
                )
                await interaction.response.send_message(embed=embed, view=Discord_View.AdminLoginView(self.ap_ctx))
                return
        
        await interaction.response.defer()

        embed = discord.Embed(
            title=_("Hint requested"),
            description=_("A hint for {location} has been requested\nCheck the log for the hint").format(location=location),
            color=discord.Color.purple()
        )

        self.ap_ctx.last_hint_location = location
        self.ap_ctx.last_hint_name = player
        self.ap_ctx.last_hint_command = "location"
        self.ap_ctx.last_hint_is_admin = True
        message = await interaction.followup.send(embed=embed)
        self.ap_ctx.pending_message = message
        await self.ap_ctx.send_msgs([{"cmd": "Say", "text": f"!admin /hint_location '{player}' '{location}'"}])
        return

    # -- Website Comamnds --
    @app_commands.command(name="add_website", description=_("Adds the website for starting the multiworld"))
    @app_commands.describe(website=_("The website to be added"))
    @commands.has_role(Admin_role_id)
    async def add_website(self, interaction: discord.Interaction, website: str):
        global Current_Website
        Current_Website = website
        Utils.persistent_store("bot", "current_website", Current_Website)
        embed = discord.Embed(
            title=_("Website added"),
            description=_("The website {website} has been added.").format(website=website),
            color=discord.Color.purple()
        )
        await interaction.response.send_message(embed=embed)

    @app_commands.command(name="list_info", description=_("Outputs info and links for the multiworld"))
    @app_commands.describe(website=_("Optional: URL; otherwise the address stored with /add_website"))
    async def list_info(self, interaction: discord.Interaction, website: str | None = None):
        global Current_Website
        url = (website or "").strip() or Current_Website
        if not url:
            embed = discord.Embed(
                title=_("No website"),
                description=_("Please use `/add_website` with a URL first or specify a URL here."),
                color=discord.Color.red(),
            )
            await interaction.response.send_message(embed=embed)
            return

        url = get_webinfo._normalize_url(url)
        await interaction.response.defer()
        ok, detail, entries = await asyncio.to_thread(get_webinfo._fetch_table_from_website, url)
        tracker_ok, tracker_detail, global_trackers = await asyncio.to_thread(
            get_webinfo._fetch_global_tracker_links_from_website, url
        )

        parsed_ok, parsed_detail, parsed_address = await asyncio.to_thread(get_webinfo._fetch_server_address_from_website, url)
        if parsed_ok and parsed_address:
            Server_Address = parsed_address

        if not ok:
            embed = discord.Embed(
                title=_("Info could not be read"),
                description=_("URL: {url}\nDetails: {detail}").format(url=url, detail=detail),
                color=discord.Color.red(),
            )
            await interaction.followup.send(embed=embed)
            return
        else:
            embed = discord.Embed(
                title=_("Info"),
                description=_("The info will be sent shortly"),
                color=discord.Color.purple(),
            )
            await interaction.followup.send(embed=embed)

        lines: list[str] = []
        for entry in entries:
            num = entry.get("index", "?")
            name = entry.get("name", "-")
            game = entry.get("game", "-")
            download = entry.get("download", "")
            tracker = entry.get("tracker", "")
            download_md = f"[{_('Download')}](https://multiworld.gg{download})" if download else _("No download")
            tracker_full = urllib.parse.urljoin(url, tracker) if tracker else ""
            tracker_md = f"[{_('Tracker')}]({tracker_full})" if tracker_full else _("Tracker: -")
            lines.append(f"{num}. {name}   |   {game}   |   {download_md}   |   {tracker_md}")

        table_text = "\n".join(lines)
        if len(table_text) > 3500:
            table_text = table_text[:3500].rstrip() + "\n..."

        embed = discord.Embed(
            title=_("Multiworld Info"),
            description=_("URL: {url}\n{detail}\nServer Address ```{server_address}```").format(url=url, detail=detail, server_address=Server_Address),
            color=discord.Color.purple(),
        )
        channel = interaction.channel
        if channel:
            await channel.send(embed=embed)
        else:
            await interaction.followup.send(embed=embed)
        
        embed = discord.Embed(
            title=_("Player list"),
            description= table_text if table_text else _("No lines found."),
            color=discord.Color.purple(),
        )
        if channel:
            await channel.send(embed=embed)
        else:
            await interaction.followup.send(embed=embed)

        mw = global_trackers.get("multiworld_tracker", "")
        sphere = global_trackers.get("sphere_tracker", "")
        tracker_lines: list[str] = []
        if mw:
            tracker_lines.append(f"[{_('Multiworld Tracker')}]({mw})")
        if sphere:
            tracker_lines.append(f"[{_('Sphere Tracker')}]({sphere})")
        trackers_text = "\n".join(tracker_lines) if tracker_lines else "-"
        if not tracker_ok and not mw and not sphere:
            trackers_text += _("\nHint: {detail}").format(detail=tracker_detail)
        embed = discord.Embed(
            title=_("Tracker"),
            description= trackers_text,
            color=discord.Color.purple(),
        )
        if channel:
            await channel.send(embed=embed)
        else:
            await interaction.followup.send(embed=embed)

    @app_commands.command(name="start_server", description=_("Starts the server via the specified website"))
    @app_commands.describe(website=_("Optional: URL; otherwise the address stored with /add_website"))
    async def start_server(self, interaction: discord.Interaction, website: str | None = None):
        global Current_Website, Server_Address, SlotName
        url = (website or "").strip() or Current_Website
        if not url:
            embed = discord.Embed(
                title=_("No website"),
                description=_("Please use `/add_website` with a URL first or specify a URL here."),
                color=discord.Color.red(),
            )
            await interaction.response.send_message(embed=embed)
            return

        url = get_webinfo._normalize_url(url)

        # Sofort bestätigen, eigentlicher Trigger läuft danach im Hintergrund.
        embed=discord.Embed(
            title=_("Start triggered"),
            description=_("The server is being started via the website {url}.").format(url=url),
            color=discord.Color.purple(),
        )

        Current_Website = url
        Utils.persistent_store("bot", "current_website", url)

        await interaction.response.send_message(embed=embed)

        success, detail = await asyncio.to_thread(get_webinfo._trigger_url, url)
        parsed_ok, parsed_detail, parsed_address = await asyncio.to_thread(get_webinfo._fetch_server_address_from_website, url)
        table_ok, table_detail, entries = await asyncio.to_thread(get_webinfo._fetch_table_from_website, url)

        auto_connect_started = False
        auto_connect_note = ""

        if table_ok and entries:
            first_slot = (entries[0].get("name", "") or "").strip()
            if first_slot:
                SlotName = first_slot
                global last_slot
                last_slot = SlotName
                Utils.persistent_store("bot", "last_slot", SlotName)
                if parsed_ok and parsed_address:
                    if not self.ap_ctx:
                        self.ap_ctx = DiscordBotContext(parsed_address, Password)
                    self.ap_ctx.server_address = parsed_address
                    self.ap_ctx.password = Password
                    self.ap_ctx.username = SlotName
                    await asyncio.sleep(4)
                    asyncio.create_task(self.ap_ctx.connect())
                    auto_connect_started = True
                    auto_connect_note = _("Automatic connection started with the first slot: `{slot_name}`.").format(slot_name=SlotName)
                else:
                    auto_connect_note = _("Auto-connect skipped because no server address was recognized.")
            else:
                auto_connect_note = _("Auto-connect skipped because no slot name was found.")
        else:
            auto_connect_note = _("Auto-connect skipped, no slots found ({detail}).").format(detail=table_detail)

        if parsed_ok and parsed_address:
            Server_Address = parsed_address
            Utils.persistent_store("client", "last_server_address", Server_Address)
        if success:
            embed = discord.Embed(
                description=(
                    _("The server was started via the website {url}.\n").format(url=url) +
                    f"{parsed_detail if parsed_ok else _('Address could not be read: {detail}').format(detail=parsed_detail)}\n" +
                    _("Current server address: {server_address}\n").format(server_address=Server_Address if parsed_ok else _('unchanged')) +
                    f"{auto_connect_note}"
                ))
        else:
            embed = discord.Embed(
                title=_("Error starting the server"),
                description=(
                    _("The server could not be started via the website {url}. {detail}\n").format(url=url, detail=detail) +
                    f"{_('Recognized address: {address}').format(address=parsed_address) if parsed_ok and parsed_address else _('Address could not be read.')}\n" +
                    f"{auto_connect_note if auto_connect_started else _('No auto-connect: {note}').format(note=auto_connect_note)}"
                ),
            )
        await interaction.edit_original_response(embed=embed)
    
    # -- Discord Comamnds --
    # Can only be used by users with the admin role
    @app_commands.command(name="change_channel", description=_("Changes the Discord channel for server output"))
    @app_commands.describe(channel=_("The new Discord channel for server output"))
    @commands.has_role(Admin_role_id)
    async def change_channel(self, interaction: discord.Interaction, channel: discord.TextChannel):
        global Channel_ID
        Channel_ID = channel.id

        Utils.persistent_store("bot", "channel_id", Channel_ID)

        embed = discord.Embed(
            title=_("Channel set"),
            description=_("Server output is now sent to <#{channel_id}>.").format(channel_id=Channel_ID),
            color=discord.Color.purple()
        )
        await interaction.response.send_message(embed=embed)
    
    @app_commands.command(name="change_language", description=_("Changes the language for the bot"))
    @app_commands.describe(language=_("The new language for the bot"))
    @app_commands.autocomplete(language=Discord_suggestions.language_suggestions)
    @commands.has_role(Admin_role_id)
    async def change_language(self, interaction: discord.Interaction, language: str):
        if language == "English":
            lang_code = "en"
        elif language == "Deutsch":
            lang_code = "de"
        else:
            embed = discord.Embed(
                title=_("Language not available"),
                description=_("The bot cannot use {language} as a language").format(language=language),
                color=discord.Color.purple()
            )
            await interaction.response.send_message(embed=embed)
            return
        
        set_language(lang_code)
        
        embed = discord.Embed(
            title=_("Language set"),
            description=_("The bot is now using the language {language}.").format(language=language),
            color=discord.Color.purple()
        )
        await interaction.response.send_message(embed=embed)

    @app_commands.command(name="help", description=_("Shows a list of all commands"))
    async def help(self, interaction: discord.Interaction):
        embed = discord.Embed(
            title=_("Help - Available Commands"),
        )
        for command in self.bot.tree.walk_commands():
            if isinstance(command, app_commands.Command):
                embed.add_field(
                    name=f"/{command.qualified_name}",
                    value=command.description or _("No description"),
                    inline=False
                )
        await interaction.response.send_message(embed=embed)

def launch(*launch_args: str):
    parser = get_base_parser(description="Discord Client interface.")
    args = parser.parse_args(launch_args)

    async def discord():
        if run_form_source:
            await bot.start(Bot_token)

    async def client():
        ctx = DiscordBotContext(None, None)
        ctx.server_task = asyncio.create_task(server_loop(ctx), name="server loop")

        if gui_enabled:
            ctx.run_gui()

        await asyncio.to_thread(ctx.run_cli)
        
        await ctx.exit_event.wait()
        await ctx.shutdown()

    async def _main():
        Utils.init_logging("DiscordClient", exception_logger="Client")
        import colorama
        colorama.just_fix_windows_console()

        await asyncio.gather(
            discord(),
            client()
        )
        colorama.deinit()

    asyncio.run(_main())

if __name__ == "__main__":
    parser = get_base_parser(description="Discord Client interface.")
    args = parser.parse_args()
    launch()