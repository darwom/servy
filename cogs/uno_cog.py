import discord
from discord.ext import commands
from uno import UnoGame  # Importiere die Uno-Spielklasse aus deiner uno.py


class UnoCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.active_games = {}  # Dictionary, um laufende Spiele zu speichern

    @commands.command(name="uno")
    async def start_uno_game(self, ctx, num_players: int = 2):
        """Startet ein neues Uno-Spiel im aktuellen Kanal"""
        if ctx.channel.id in self.active_games:
            await ctx.send("Es läuft bereits ein Uno-Spiel in diesem Kanal.")
            return

        game = UnoGame(num_players)
        self.active_games[ctx.channel.id] = game
        await ctx.send(f"Ein neues Uno-Spiel mit {num_players} Spielern wurde gestartet!")

        await self.play_uno_game(ctx, game)

    async def play_uno_game(self, ctx, game: UnoGame):
        """Der Hauptspiel-Loop für UNO, interagierend über Discord-Nachrichten"""
        game.reset_game()
        await ctx.send(f"Das Uno-Spiel beginnt!")

        while True:
            current_player = game.current_player
            if current_player == 0:
                # Spieler 0 ist der Mensch, der über Discord interagiert
                await ctx.send(f"Du bist am Zug. Oberste Karte: {game.discard_pile[-1]}")
                await ctx.send(f"Deine Hand: {game.players[0]}")
                await ctx.send("Mögliche Karten zu spielen oder 'ziehen' eingeben um zu ziehen:")

                valid_actions = game.get_valid_actions()
                action_dict = {str(i + 1): action for i, action in enumerate(valid_actions)}
                action_options = "\n".join(f"{i}: {action}" for i, action in action_dict.items())
                await ctx.send(f"{action_options}\n'ziehen': Karte ziehen")

                def check(m):
                    return m.author == ctx.author and m.channel == ctx.channel

                try:
                    msg = await self.bot.wait_for('message', check=check, timeout=60.0)
                    if msg.content.lower() == "ziehen":
                        action = None
                    else:
                        action = action_dict.get(msg.content)
                    await self.handle_turn(ctx, game, action)
                except Exception as e:
                    await ctx.send(f"Fehler oder Zeitüberschreitung: {str(e)}")
                    self.handle_turn(ctx, game, None)

            else:
                await ctx.send(f"KI-Spieler {current_player} ist am Zug.")
                state = game.encode_state()
                valid_actions = game.get_valid_actions()
                action = game.nn.act(state, valid_actions)
                await self.handle_turn(ctx, game, action)

            if game.check_winner() is not None:
                winner = game.check_winner()
                await ctx.send(f"Spieler {winner} gewinnt das Spiel!")
                del self.active_games[ctx.channel.id]
                break

    async def handle_turn(self, ctx, game, action):
        """Verarbeitet den Spielzug eines Spielers"""
        _, _, reward, _, done = game.step(action)
        await ctx.send(f"Belohnung für diesen Zug: {reward}")

    @commands.command(name="stop_uno")
    async def stop_uno_game(self, ctx):
        """Beendet ein laufendes Uno-Spiel im aktuellen Kanal"""
        if ctx.channel.id in self.active_games:
            del self.active_games[ctx.channel.id]
            await ctx.send("Das Uno-Spiel wurde beendet.")
        else:
            await ctx.send("Kein Uno-Spiel läuft in diesem Kanal.")


async def setup(bot):
    await bot.add_cog(UnoCog(bot))
