from .cog import Dice
from .exploration import Exploration

def setup(bot):
    bot.add_cog(Dice(bot))
    #bot.add_cog(Exploration(bot))
