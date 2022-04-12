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
from .inline import InlineRoller
from .cog import Dice
from .utils import string_search_adv
import disnake
from disnake.ext import commands
from disnake.ext.commands import NoPrivateMessage

from ..initiative import Combatant

#EXPLORATION_TTL = 60 * 60 * 24 * 7  # 1 week TTL

#class Exploration(commands.Cog):

    # cache exploration for 10 seconds to avoid race conditions
    # this makes sure that multiple calls to Exploration.from_ctx() in the same invocation or two simultaneous ones
    # retrieve/modify the same Exploration state
    # caches based on channel id
    # probably won't encounter any scaling issues, since an exploration will be shard-specific
    #_cache = cachetools.TTLCache(maxsize=50, ttl=10)
    #def __init__(
   # #    self,
     #   channel_id: str,
     #   message_id: int,
     #   dm_id: str,
     #   options: dict,
     #   ctx: disnake.ext.commands.Context,
     #   explorers: List[Combatant] = None,
     #   round_num: int = 0,
     #   turn_num: int = 0,
     #   current_index: Optional[int] = None,






  #  @commands.command(name="explore")
  #  async def quick_roll(self, ctx, *, mod: str = "0"):
   #     """Quickly rolls a d12+d8."""
   #     dice = "1d12+1d8+" + mod
   #     adv = string_search_adv(dice)
   #     res = d20.roll(dice, advantage=adv, allow_comments=True, stringifier=VerboseMDStringifier())
   #     out = f"{ctx.author.mention}  :game_die:\n" f"{str(res)}"
   #     await try_delete(ctx.message)
   #     await ctx.send(out, allowed_mentions=discord.AllowedMentions(users=[ctx.author]))
   #     await Stats.increase_stat(ctx, "dice_rolled_life")
   #     if gamelog := self.bot.get_cog("GameLog"):
   #         await gamelog.send_roll(ctx, res)
