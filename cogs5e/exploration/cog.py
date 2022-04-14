import random

import cachetools
import d20
import discord
from discord.ext import commands

from typing import Any, List, Optional, TYPE_CHECKING
from aliasing import helpers
from cogs5e.models.errors import NoSelectionElements
from cogs5e.utils import actionutils, checkutils, targetutils
from cogs5e.utils.help_constants import *
from cogsmisc.stats import Stats
from gamedata import Monster
from gamedata.lookuputils import handle_source_footer, select_monster_full, select_spell_full
from utils.argparser import argparse
from utils.constants import SKILL_NAMES
from utils.dice import PersistentRollContext, VerboseMDStringifier
from utils.functions import search_and_select, try_delete
from cogs5e.dice.inline import InlineRoller
from cogs5e.dice.cog import Dice
from cogs5e.dice.utils import string_search_adv
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
