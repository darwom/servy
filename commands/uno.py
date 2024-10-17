import discord
from discord.ext import commands
import services.uno_game_service as un


class Uno(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.active_games = {}  # Store active games by channel or user ID

    @commands.command(name='play_uno_cmd')
    async def start_uno_game(self, ctx):
        if ctx.channel.id in self.active_games:
            await ctx.send("There is already an active UNO game in this channel!")
            return

        # Initialize a new game for the channel
        game = un.UnoGame(num_players=2)
        game.nn.load_experience('uno_experience_memory.pkl')

        self.active_games[ctx.channel.id] = game
        await ctx.send("Started a new UNO game! Use `!draw` to draw a card or `!play <card>` to play a card.")

    @commands.command(name='draw')
    async def draw_card(self, ctx):
        game = self.active_games.get(ctx.channel.id)
        if not game:
            await ctx.send("No active UNO game found. Start one with `!play_uno_cmd`.")
            return

        drawn_cards = game.draw_cards(0, 1)  # Assume player 0 is the user
        card_names = ', '.join(str(card) for card in drawn_cards)
        await ctx.send(f"You drew: {card_names}")

        # Show player's hand after drawing a card
        player_hand = game.players[0]
        hand_list = ', '.join(str(card) for card in player_hand)
        await ctx.send(f"Your hand: {hand_list}")

    @commands.command(name='play')
    async def play_card(self, ctx, *card_info):
        game = self.active_games.get(ctx.channel.id)
        if not game:
            await ctx.send("No active UNO game found. Start one with `!play_uno_cmd`.")
            return

        # Convert card_info into card
        card_str = ' '.join(card_info)
        player_hand = game.players[0]
        for card in player_hand:
            if str(card).lower() == card_str.lower():
                if game.play_card(0, card):
                    await ctx.send(f"You played: {card}")
                    break
        else:
            await ctx.send(f"You don't have that card or it's not playable.")

        # Show player's hand after playing a card
        player_hand = game.players[0]
        hand_list = ', '.join(str(card) for card in player_hand)
        await ctx.send(f"Your hand: {hand_list}")

        # Check and handle AI's turn
        if not game.check_winner():
            await self.play_ai_turn(ctx, game)
        else:
            winner = game.check_winner()
            await ctx.send(f"Game over! Player {winner} wins!")
            self.active_games.pop(ctx.channel.id, None)

    async def play_ai_turn(self, ctx, game):
        state = game.encode_state()
        valid_actions = game.get_valid_actions()
        action = game.nn.act(state, valid_actions)

        if action is None:
            game.draw_cards(1, 1)  # AI draws card
            await ctx.send("AI drew a card.")
        else:
            game.play_card(1, action)  # AI plays card
            await ctx.send(f"AI played: {action}")

        if game.check_winner():
            winner = game.check_winner()
            await ctx.send(f"Game over! Player {winner} wins!")
            self.active_games.pop(ctx.channel.id, None)


# Add the Uno bot cog to the bot
async def setup(bot):
    await bot.add_cog(Uno(bot))
