import random
from contextlib import suppress
import collections
import functools
import cachetools
import d20
import discord
from discord.ext import commands

from typing import Any, List, Optional, TYPE_CHECKING
from aliasing import helpers
from cogs5e.exploration.explore import Explore
from cogs5e.models.character import Character
from cogs5e.models.errors import NoSelectionElements
from cogs5e.utils import actionutils, checkutils, targetutils
from cogs5e.utils.help_constants import *
from cogsmisc.stats import Stats
from cogs5e.models.embeds import EmbedWithAuthor, EmbedWithCharacter, EmbedWithColor
from gamedata.lookuputils import handle_source_footer, select_monster_full, select_spell_full
from utils.argparser import argparse
from utils.constants import SKILL_NAMES
from utils import checks, constants
from utils.argparser import argparse
from utils.functions import confirm, get_guild_member, search_and_select, try_delete
from utils.functions import search_and_select, try_delete
from cogs5e.dice.inline import InlineRoller
from cogs5e.dice.cog import Dice
from cogs5e.dice.utils import string_search_adv
from cogs5e.exploration.explorer import Explorer, PlayerExplorer
from cogs5e.exploration.effect import Effect
from . import utils
import disnake
from disnake.ext import commands
from disnake.ext.commands import NoPrivateMessage


class ExplorationTracker(commands.Cog):

    def __init__(self, bot):
        self.bot = bot

    async def cog_check(self, ctx):
        if ctx.guild is None:
            raise NoPrivateMessage()
        return True

    async def cog_before_invoke(self, ctx):
        await try_delete(ctx.message)

    # ==== commands ====
    @commands.group(aliases=["e"], invoke_without_command=True)
    async def explore(self, ctx):
        """Commands to help exploration."""
        await ctx.send(f"Incorrect usage. Use {ctx.prefix}help explore for help.")

    @explore.command()
    async def begin(self, ctx, *args):
        """Begins exploration in the channel the command is invoked.
        Usage: !explore begin <ARGS (opt)>
        __Valid Argument__
        -name <name> - Sets a name for the combat instance."""
        await Explore.ensure_unique_chan(ctx)

        guild_settings = await ctx.get_server_settings()

        options = {}
        args = argparse(args)
        if "name" in args:
            options["name"] = args.last("name")

        temp_summary_msg = await ctx.send("```Awaiting explorers...```")

        exploration = Explore.new(str(ctx.channel.id), temp_summary_msg.id, str(ctx.author.id), options, ctx)

        with suppress(disnake.HTTPException):
            await temp_summary_msg.pin()
        out = (
            f"If you have a character set up with SheetManager: `{ctx.prefix}explore join`\n"
            f"Otherwise: `{ctx.prefix}explore add <name>`"
        )

        await exploration.final()
        await ctx.send(out)

    @explore.command()
    async def add(self, ctx, modifier: int, name: str, *args):
        """Adds a generic explorer to the initiative order.
        If a character is set up with the SheetManager module, you can use !explore join instead.
        If you are adding monsters to combat, you can use !init madd instead.

        __Valid Arguments__
        `-controller <controller>` - Pings a different person on turn.
        `-group <group>` - Adds the combatant to a group.
        `-note <note>` - Sets the combatant's note.
        """

        controller = str(ctx.author.id)
        group = None

        args = argparse(args)

        if args.last("controller"):
            controller_name = args.last("controller")
            member = await commands.MemberConverter().convert(ctx, controller_name)
            controller = str(member.id) if member is not None and not member.bot else controller
        if args.last("group"):
            group = args.last("group")

        note = args.last("note")

        exploration = await ctx.get_exploration()

        if exploration.get_explorer(name, True) is not None:
            await ctx.send("Explorer already exists.")
            return

        me = Explorer.new(
            name, controller, ctx, exploration
        )

        # -note (#1211)
        if note:
            me.notes = note

        if group is None:
            exploration.add_explorer(me)
            await ctx.send(f"{name} was added to exploration.")
        else:
            grp = exploration.get_group(group)
            grp.add_explorer(me)
            await ctx.send(f"{name} was added to exploration as part of group {grp.name}.")

        await exploration.final()

    @explore.command(name="join", aliases=["cadd", "dcadd"])
    async def join(self, ctx, *, args: str = ""):
        """
        Adds the current active character to combat. A character must be loaded through the SheetManager module first.
        __Valid Arguments__
        `-phrase <phrase>` - Adds flavor text.
        `-thumb <thumbnail URL>` - Adds flavor image.
        `-group <group>` - Adds the combatant to a group.
        `-note <note>` - Sets the combatant's note.
        [user snippet]
        """
        char: Character = await ctx.get_character()
        args = await helpers.parse_snippets(args, ctx, character=char)
        args = argparse(args)

        embed = EmbedWithCharacter(char, False)

        group = args.last("group")
        note = args.last("note")
        check_result = None

        args.ignore("rr")
        args.ignore("dc")

        controller = str(ctx.author.id)

        exploration = await ctx.get_exploration()

        if exploration.get_explorer(char.name, True) is not None:
            await ctx.send("Explorer already exists.")
            return

        me = await PlayerExplorer.from_character(char, ctx, exploration, controller)

        # -note (#1211)
        if note:
            me.notes = note

        if group is None:
            exploration.add_explorer(me)
            embed.set_footer(text="Added to combat!")
        else:
            grp = exploration.get_group(group)
            grp.add_combatant(me)
            embed.set_footer(text=f"Joined group {grp.name}!")

        await exploration.final()
        await ctx.send(embed=embed)

    @explore.command(name="advance", aliases=["adv", "a"])
    async def advance(self, ctx, numrounds: int = 1):
        """Skips one or more rounds of initiative."""
        exploration = await ctx.get_exploration()

        messages = exploration.skip_rounds(numrounds)
        out = messages

        if (turn_str := exploration.get_turn_str()) is not None:
            out.append(turn_str)
        else:
            out.append(exploration.get_summary())

        await ctx.send("\n".join(out), allowed_mentions=exploration.get_turn_str_mentions())
        await exploration.final()

    @explore.command(name="list", aliases=["summary"])
    async def list(self, ctx, *args):
        """Lists the explorers.
        __Valid Arguments__
        private - Sends the list in a private message."""
        exploration = await ctx.get_exploration()
        private = "private" in args
        destination = ctx if not private else ctx.author
        if private and str(ctx.author.id) == exploration.dm:
            out = exploration.get_summary(True)
        else:
            out = exploration.get_summary()
        await destination.send(out)

    @explore.command()
    async def note(self, ctx, name: str, *, note: str = ""):
        """Attaches a note to an explorer."""
        exploration = await ctx.get_exploration()

        explorer = await exploration.select_explorer(name)
        if explorer is None:
            return await ctx.send("Explorer not found.")

        explorer.notes = note
        if note == "":
            await ctx.send("Removed note.")
        else:
            await ctx.send("Added note.")
        await exploration.final()

    @explore.command(aliases=["opts"])
    async def opt(self, ctx, name: str, *args):
        """
        Edits the options of a combatant.
        __Valid Arguments__
        `-name <name>` - Changes the combatants' name.
        `-controller <controller>` - Pings a different person on turn.
        """  # noqa: E501
        exploration = await ctx.get_exploration()

        expl = await exploration.select_explorer(name, select_group=True)
        if expl is None:
            await ctx.send("Explorer not found.")
            return

        args = argparse(args)
        options = {}
        run_once = set()
        allowed_mentions = set()

        def option(opt_name=None, pass_group=False, **kwargs):
            """
            Wrapper to register an option.
            :param str opt_name: The string to register the function under. Defaults to function name.
            :param bool pass_group: Whether to pass a group as the first argument to the function or a combatant.
            :param kwargs: kwargs that will always be passed to the function.
            """

            def wrapper(func):
                target_is_group = False;
                func_name = opt_name or func.__name__
                if pass_group and target_is_group:
                    old_func = func

                    async def func(_, *a, **k):
                        if func_name in run_once:
                            return
                        run_once.add(func_name)
                        return await old_func(expl, *a, **k)  # pop the combatant argument and sub in group

                func = options[func_name] = functools.partial(func, **kwargs)
                return func

            return wrapper

        def mod_or_set(opt_name, old_value):
            new_value = args.last(opt_name, type_=int)
            if args.last(opt_name).startswith(("-", "+")):
                new_value = (old_value or 0) + new_value
            return new_value, old_value

        @option()
        async def controller(explorer):
            controller_name = args.last("controller")
            member = await commands.MemberConverter().convert(ctx, controller_name)
            if member is None:
                return "\u274c New controller not found."
            if member.bot:
                return "\u274c Bots cannot control combatants."
            allowed_mentions.add(member)
            explorer.controller = str(member.id)
            return f"\u2705 {explorer.name}'s controller set to {explorer.controller_mention()}."

        @option(pass_group=True)
        async def name(explorer):
            old_name = explorer.name
            new_name = args.last("name")
            if exploration.get_explorer(new_name, True) is not None:
                return f"\u274c There is already another combatant with the name {new_name}."
            elif new_name:
                explorer.name = new_name
                return f"\u2705 {old_name}'s name set to {new_name}."
            else:
                return "\u274c You must pass in a name with the -name tag."

        # run options
        targets = [expl]
        out = collections.defaultdict(lambda: [])

        for arg_name, opt_func in options.items():
            if arg_name in args:
                for target in targets:
                    response = await opt_func(target)
                    if response:
                        if target.is_private:
                            destination = (await get_guild_member(ctx.guild, int(expl.controller))) or ctx.channel
                        else:
                            destination = ctx.channel
                        out[destination].append(response)

        if out:
            for destination, messages in out.items():
                await destination.send(
                    "\n".join(messages), allowed_mentions=disnake.AllowedMentions(users=list(allowed_mentions))
                )
            await exploration.final()
        else:
            await ctx.send("No valid options found.")
