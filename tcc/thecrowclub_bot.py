from typing import Final
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes
import asyncio
import random
from blackjack_game import BlackjackGame, Card

def calculate_blackjack_score(hand):
    """Calcula a pontuacao da mao com a regra classica do Blackjack."""
    score = 0
    aces = 0
    
    for card in hand:
        if card.value in ['J', 'Q', 'K']:
            score += 10
        elif card.value == 'A':
            aces += 1
            score += 11
        elif card.value == 'Joker':
            score += 0
        else:
            score += int(card.value)

    while score > 21 and aces > 0:
        score -= 10
        aces -= 1
    
    return score

def find_user_session(user_id):
    """Find the active session for a user across all chats"""
    for chat_id, session in active_sessions.items():
        if user_id in session.players:
            return chat_id, session
    return None, None

# configurações do bot
TOKEN: Final = '7760039811:AAE-JNN14Gd5ZodjP9xpDakRyde1qKBuD5k'
BOT_USERNAME: Final = '@TheCrowClub_bot'

# estrutura para armazenar jogos ativos e seus jogadores
class GameSession:
    def __init__(self, host_id):
        self.game = BlackjackGame()
        self.players = {}  # user_id: {hand: [], total: 0, stand: False, message_id: None, curses: []}
        self.host_id = host_id
        self.max_players = 6
        self.min_players = 2
        self.started = False
        self.current_round = 1
        self.max_rounds = 5
        self.votes_continue = set()
        self.votes_end = set()
        self.scores = {}  # user_id: pontos totais
        self.round_winners = []  # lista de vencedores da rodada atual
        self.player_order = []  # ordem dos jogadores para jogar
        self.current_player_index = 0  # índice do jogador atual

active_sessions = {}  # chat_id: GameSession

async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "Bem-vindo ao Crow Club.\n\n"
        "Aqui, os jogos têm um preço além das fichas...\n"
        "Comandos disponíveis:\n"
        "/create_blackjack - Cria uma nova mesa de Blackjack\n"
        "/join - Entra na mesa atual\n"
        "/start_game - Inicia o jogo (apenas para o criador)\n"
        "/hit - Pede mais uma carta\n"
        "/stand - Mantém suas cartas\n"
        "/leave - Sair da mesa.\n"
        "/kill - Encerra a partida (apenas para o criador)\n"
        "/rules - Regras do Blackjack\n"
        "/continue - Vota para continuar após 5 rodadas\n"
        "/end - Vota para encerrar após 5 rodadas"
    )

async def leave_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.message.chat_id
    user_id = update.message.from_user.id
    
    if chat_id not in active_sessions:
        await update.message.reply_text("Não há jogo ativo neste chat.")
        return
        
    session = active_sessions[chat_id]
    
    if user_id not in session.players:
        await update.message.reply_text("Você não está participando deste jogo.")
        return

    if session.started:
        player = session.players[user_id]
        cards_text = "\n".join([f"{card.value} de {card.suit}" for card in player["hand"]])
        
        await update.message.reply_text(
            "🃏 As cartas em sua mão se recusam a deixar você ir. Você não pode deixar o jogo até o final da partida.\n\n"
            "As cartas parecem apertar controlar sua vontade, lembrando que você fez um pacto ao entrar no jogo."
        )
        return
        
    session.players.pop(user_id, None)
    session.scores.pop(user_id, None)
    await update.message.reply_text("Você saiu da mesa. Sorte sua que o jogo ainda não havia começado...")

async def create_blackjack_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.message.chat_id
    user_id = update.message.from_user.id
    
    if chat_id in active_sessions:
        await update.message.reply_text("Já existe uma mesa ativa neste chat.")
        return
        
    session = GameSession(user_id)
    session.players[user_id] = {"hand": [], "total": 0, "stand": False, "message_id": None, "curses": []}
    session.scores[user_id] = 0
    active_sessions[chat_id] = session
    
    await update.message.reply_text(
        "🎲 Mesa de Blackjack criada!\n"
        "Outros jogadores podem entrar usando /join@TheCrowClub_bot\n"
        "São necessários no mínimo 2 jogadores para começar.\n"
        "Quando todos estiverem prontos, use /start_game@TheCrowClub_bot"
    )

async def join_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.message.chat_id
    user_id = update.message.from_user.id
    
    if chat_id not in active_sessions:
        await update.message.reply_text("Não há mesa ativa neste chat.")
        return
        
    session = active_sessions[chat_id]
    
    if session.started:
        await update.message.reply_text("O jogo já começou.")
        return
        
    if len(session.players) >= session.max_players:
        await update.message.reply_text("Mesa cheia.")
        return
        
    if user_id in session.players:
        await update.message.reply_text("Você já está na mesa.")
        return
        
    session.players[user_id] = {"hand": [], "total": 0, "stand": False, "message_id": None, "curses": []}
    session.scores[user_id] = 0
    await update.message.reply_text(f"Jogador {update.message.from_user.first_name} entrou na mesa!")

async def start_game_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.message.chat_id
    user_id = update.message.from_user.id
    
    if chat_id not in active_sessions:
        await update.message.reply_text("Não há mesa ativa neste chat.")
        return
        
    session = active_sessions[chat_id]
    
    if user_id != session.host_id:
        await update.message.reply_text("Apenas o criador da mesa pode iniciar o jogo.")
        return
        
    if session.started:
        await update.message.reply_text("O jogo já começou.")
        return

    if len(session.players) < session.min_players:
        await update.message.reply_text("São necessários no mínimo 2 jogadores para começar.")
        return
        
    session.started = True

    # apresentação dos jogadores e dealer
    players_list = []

    for player_id in session.players.keys():
        member = await context.bot.get_chat_member(chat_id, player_id)
        players_list.append(f"• {member.user.first_name}")

    players_text = "\n".join(players_list)

    await update.message.reply_text(
        "🎭 Bem-vindos ao Crow Club! 🎭\n\n"
        "Seu dealer hoje será Kaz Brekker, o proprietário do Clube do Corvo.\n"
        "Jogadores na mesa:\n"
        f"{players_text}\n\n"
        f"🎲 Iniciando rodada {session.current_round} de {session.max_rounds}!\n"
        "Pegue suas cartas iniciais: /hit@TheCrowClub_bot"
    )
async def check_round_end(chat_id, session, context):
    if all(player["stand"] for player in session.players.values()):
        session.round_winners = []
        max_valid_total = 0

        for player_id, data in session.players.items():
            if data["total"] == 21:
                session.round_winners.append(player_id)
                session.scores[player_id] = session.scores.get(player_id, 0) + 2

        if not session.round_winners:
            for player_id, data in session.players.items():
                if data["total"] <= 21:
                    if data["total"] > max_valid_total:
                        max_valid_total = data["total"]
                        session.round_winners = [player_id]
                    elif data["total"] == max_valid_total:
                        session.round_winners.append(player_id)

            for winner_id in session.round_winners:
                session.scores[winner_id] = session.scores.get(winner_id, 0) + 1

        round_summary = f"Resultados da rodada {session.current_round}:\n"
        for player_id, data in session.players.items():
            user = await context.bot.get_chat_member(chat_id, player_id)
            cards_text = ", ".join([f"{card.value} de {card.suit}" for card in data["hand"]])

            if data["total"] > 21:
                status = "Estourou"
            elif player_id in session.round_winners:
                status = "Venceu"
            else:
                status = "Perdeu"

            round_summary += f"\n- {user.user.first_name}: {cards_text} (Total: {data['total']}) - {status}"

        await context.bot.send_message(chat_id, round_summary)

        if session.round_winners:
            winners_text = ""
            for winner_id in session.round_winners:
                user = await context.bot.get_chat_member(chat_id, winner_id)
                points = session.players[winner_id]["total"]
                winners_text += f"\n- {user.user.first_name} com {points} pontos!"

            await context.bot.send_message(
                chat_id,
                f"Fim da rodada {session.current_round}!\n"
                f"Vencedor(es):{winners_text}\n"
                "Pontuação atual:"
                + "\n".join([f"\n- {(await context.bot.get_chat_member(chat_id, pid)).user.first_name}: {score} pontos"
                            for pid, score in session.scores.items()])
            )
        else:
            await context.bot.send_message(
                chat_id,
                f"Fim da rodada {session.current_round}!\n"
                "Nenhum vencedor nesta rodada - todos ultrapassaram 21!"
            )

        session.current_round += 1

        if session.current_round > session.max_rounds:
            if session.max_rounds == 5:
                max_score = max(session.scores.values())
                winners = [pid for pid, score in session.scores.items() if score == max_score]

                if len(winners) > 1:
                    session.max_rounds = 10
                    await context.bot.send_message(
                        chat_id,
                        "Temos um empate! O jogo continuará automaticamente até 10 rodadas para desempate!"
                    )
                    await start_new_round(chat_id, session, context)
                    return
                else:
                    await context.bot.send_message(
                        chat_id,
                        "Fim das 5 rodadas iniciais!\nUse /continue para votar em mais 5 rodadas\nOu /end para encerrar o jogo"
                    )
            else:
                max_score = max(session.scores.values())
                final_winners = [pid for pid, score in session.scores.items() if score == max_score]

                if len(final_winners) == 1:
                    final_winner_id = final_winners[0]
                    losers = [player_id for player_id in session.players.keys() if player_id != final_winner_id]

                    winner = await context.bot.get_chat_member(chat_id, final_winner_id)
                    winner_name = winner.user.first_name

                    winners_msg = (
                        f"Fim do jogo!\n"
                        f"Grande vencedor: {winner_name} com {max_score} pontos!\n"
                        "As maldições foram neutralizadas para o vencedor!"
                    )

                    losers_msg = "\n\nPerdedores e suas maldições:"
                    for loser_id in losers:
                        user = await context.bot.get_chat_member(chat_id, loser_id)
                        curses = [f"- {curse.curse}" for curse in session.players[loser_id]["curses"]]
                        curse_hours = random.randint(1, 24)
                        if curses:
                            curses_text = "\n".join(curses)
                            losers_msg += f"\n\n{user.user.first_name} sofrerá por {curse_hours} horas:\n{curses_text}"
                        else:
                            losers_msg += f"\n\n{user.user.first_name} escapou sem maldições!"

                    await context.bot.send_message(chat_id, winners_msg + losers_msg)
                    del active_sessions[chat_id]
                else:
                    winners_names = [
                        (await context.bot.get_chat_member(chat_id, winner_id)).user.first_name
                        for winner_id in final_winners
                    ]
                    await context.bot.send_message(
                        chat_id,
                        f"Fim do jogo!\nHouve um empate entre: {', '.join(winners_names)}\n"
                        f"Cada um com {max_score} pontos!\nTodos os empatados terão suas maldições neutralizadas!"
                    )
                    del active_sessions[chat_id]
        else:
            await start_new_round(chat_id, session, context)

async def start_new_round(chat_id, session, context):
    session.game = BlackjackGame()

    for player_id in list(session.players.keys()):
        session.players[player_id]["hand"] = []
        session.players[player_id]["total"] = 0
        session.players[player_id]["stand"] = False
        session.players[player_id]["message_id"] = None

    await context.bot.send_message(
        chat_id,
        f"Iniciando rodada {session.current_round} de {session.max_rounds}!\n"
        "Pegue suas cartas iniciais: /hit@TheCrowClub_bot"
    )

async def hit_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id

    chat_id, session = find_user_session(user_id)

    if session is None:
        await update.message.reply_text("Você não está participando de nenhum jogo ativo.")
        return

    if user_id not in session.players:
        await update.message.reply_text("Você não está participando deste jogo.")
        return

    if session.players[user_id]["stand"]:
        await update.message.reply_text("Você já deu stand nesta rodada.")
        return

    player = session.players[user_id]
    user = update.message.from_user

    if not player["hand"]:
        player["hand"] = [session.game._draw_card(), session.game._draw_card()]
    else:
        player["hand"].append(session.game._draw_card())

    total = calculate_blackjack_score(player["hand"])
    player["total"] = total
    cards_text = "\n".join([f"{card.value} de {card.suit}" for card in player["hand"]])

    private_message = f"Suas cartas:\n{cards_text}\nTotal: {total}\n\n"

    if total == 21:
        private_message += "Blackjack! 21 pontos!"
        player["stand"] = True
        await context.bot.send_message(user_id, private_message)
        await context.bot.send_message(chat_id, f"{user.first_name} finalizou a rodada.")
        await check_round_end(chat_id, session, context)
    elif total > 21:
        if any(card.value == "Joker" for card in player["hand"]):
            all_curses = session.game._create_deck()
            curse_card = random.choice(all_curses)
        else:
            curse_card = random.choice(player["hand"])

        player["curses"].append(curse_card)

        private_message = (
            f"Você ultrapassou 21 com {total} pontos!\n"
            f"A maldição recai sobre você através da carta:\n"
            f"{curse_card.value} de {curse_card.suit}\n"
            f"Sua punição será:\n"
            f"{curse_card.curse}"
        )
        await context.bot.send_message(user_id, private_message)
        player["stand"] = True
        await context.bot.send_message(chat_id, f"{user.first_name} finalizou a rodada.")
        await check_round_end(chat_id, session, context)
    else:
        private_message += "Use /hit para mais uma carta ou /stand para manter"
        await context.bot.send_message(user_id, private_message)
        await context.bot.send_message(chat_id, f"{user.first_name} pediu uma carta!")

async def stand_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id

    chat_id, session = find_user_session(user_id)

    if session is None:
        await update.message.reply_text("Você não está participando de nenhum jogo ativo.")
        return

    if user_id not in session.players:
        await update.message.reply_text("Você não está participando deste jogo.")
        return

    if session.players[user_id]["stand"]:
        await update.message.reply_text("Você já deu stand nesta rodada.")
        return

    player = session.players[user_id]
    user = update.message.from_user

    if not player["hand"]:
        await update.message.reply_text("Você precisa pegar suas cartas iniciais primeiro com /hit")
        return

    player["stand"] = True
    total = player["total"]

    cards_text = "\n".join([f"{card.value} de {card.suit}" for card in player["hand"]])
    private_message = f"Suas cartas:\n{cards_text}\nTotal: {total}\n\nVocê manteve suas cartas!"
    await context.bot.send_message(user_id, private_message)
    await context.bot.send_message(chat_id, f"{user.first_name} finalizou a rodada.")

    await check_round_end(chat_id, session, context)

async def continue_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id
    
    # Find the user's active session
    chat_id, session = find_user_session(user_id)
    
    if session is None:
        await update.message.reply_text("Você não está participando de nenhum jogo ativo.")
        return
    
    if session.current_round <= 5 or session.max_rounds > 5:
        await update.message.reply_text("Este comando só pode ser usado após as 5 rodadas iniciais.")
        return
        
    if user_id not in session.players:
        await update.message.reply_text("Você não está participando deste jogo.")
        return
        
    session.votes_continue.add(user_id)
    
    # Se tiver apenas 2 jogadores e votarem diferente
    if len(session.players) == 2 and len(session.votes_continue) == 1 and len(session.votes_end) == 1:
        await update.message.reply_text("Os jogadores votaram em opções diferentes! O dealer irá sortear o resultado...")
        if random.choice([True, False]):
            session.max_rounds = 10
            await update.message.reply_text("O dealer sorteou: O jogo continuará até 10 rodadas!")
            await start_new_round(chat_id, session, context)
        else:
            await end_game(chat_id, session, context)
        session.votes_continue.clear()
        session.votes_end.clear()
        return
    
    if len(session.votes_continue) == len(session.players):
        session.max_rounds = 10
        session.votes_continue.clear()
        await update.message.reply_text("Todos concordaram! O jogo continuará até 10 rodadas!")
        await start_new_round(chat_id, session, context)
    else:
        remaining = len(session.players) - len(session.votes_continue)
        await update.message.reply_text(f"Voto registrado! Faltam {remaining} jogador(es) votarem.")

async def end_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id
    
    # Find the user's active session
    chat_id, session = find_user_session(user_id)
    
    if session is None:
        await update.message.reply_text("Você não está participando de nenhum jogo ativo.")
        return
    
    if session.current_round <= 5:
        await update.message.reply_text("Este comando só pode ser usado após as 5 rodadas iniciais.")
        return
        
    if user_id not in session.players:
        await update.message.reply_text("Você não está participando deste jogo.")
        return
        
    session.votes_end.add(user_id)
    
    # Se tiver apenas 2 jogadores e votarem diferente
    if len(session.players) == 2 and len(session.votes_continue) == 1 and len(session.votes_end) == 1:
        await update.message.reply_text("Os jogadores votaram em opções diferentes! O dealer irá sortear o resultado...")
        if random.choice([True, False]):
            session.max_rounds = 10
            await update.message.reply_text("O dealer sorteou: O jogo continuará até 10 rodadas!")
            await start_new_round(chat_id, session, context)
        else:
            await end_game(chat_id, session, context)
        session.votes_continue.clear()
        session.votes_end.clear()
        return
    
    min_votes_needed = len(session.players) // 2  # Arredonda para baixo em caso de número ímpar
    
    if len(session.votes_end) >= min_votes_needed:
        await end_game(chat_id, session, context)
    else:
        remaining = min_votes_needed - len(session.votes_end)
        await update.message.reply_text(f"Voto para encerrar registrado! Faltam {remaining} voto(s) para encerrar o jogo.")

async def end_game(chat_id, session, context):
    # Encontrar vencedor final
    max_score = max(session.scores.values())
    final_winners = [pid for pid, score in session.scores.items() if score == max_score]
    
    if len(final_winners) == 1:
        final_winner_id = final_winners[0]
        losers = [player_id for player_id in session.players.keys() if player_id != final_winner_id]
        
        winner = await context.bot.get_chat_member(chat_id, final_winner_id)
        winner_name = winner.user.first_name
        
        winners_msg = (
            f"🎉 Fim do jogo!\n"
            f"Grande vencedor: {winner_name} com {max_score} pontos!\n"
            f"As maldições foram neutralizadas para o vencedor!"
        )
        
        losers_msg = "\n\nPerdedores e suas maldições:"
        for loser_id in losers:
            user = await context.bot.get_chat_member(chat_id, loser_id)
            curses = [f"- {curse.curse}" for curse in session.players[loser_id]["curses"]]
            curse_hours = random.randint(1, 24)
            if curses:
                curses_text = "\n".join(curses)
                losers_msg += f"\n\n{user.user.first_name} sofrerá por {curse_hours} horas:\n{curses_text}"
            else:
                losers_msg += f"\n\n{user.user.first_name} escapou sem maldições!"
        
        await context.bot.send_message(chat_id, winners_msg + losers_msg)
    else:
        # Se houver empate
        winners_names = [
            (await context.bot.get_chat_member(chat_id, winner_id)).user.first_name 
            for winner_id in final_winners
        ]
        await context.bot.send_message(
            chat_id,
            f"🎉 Fim do jogo!\nHouve um empate entre: {', '.join(winners_names)}\n"
            f"Cada um com {max_score} pontos!\nTodos os empatados terão suas maldições neutralizadas!"
        )
    
    del active_sessions[chat_id]

async def kill_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.message.chat_id
    user_id = update.message.from_user.id
    
    if chat_id not in active_sessions:
        await update.message.reply_text("Não há jogo ativo neste chat.")
        return
        
    session = active_sessions[chat_id]
    
    if user_id != session.host_id:
        await update.message.reply_text("Apenas o criador da mesa pode encerrar o jogo.")
        return

    del active_sessions[chat_id]
    await update.message.reply_text("O jogo foi encerrado pelo criador da mesa.")

async def rules_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "📜 Regras do Blackjack:\n\n"
        "1. De 2 a 6 jogadores por mesa\n"
        "2. Cada jogador recebe 2 cartas iniciais\n"
        "3. O objetivo é chegar o mais próximo de 21 sem ultrapassar\n"
        "4. Cartas numéricas valem seu número\n"
        "5. J, Q e K valem 10\n"
        "6. Ás vale 1 ou 11, no valor que for melhor para a mão\n"
        "7. Joker vale 0\n"
        "8. Se ultrapassar 21, você será amaldiçoado por uma carta aleatória da sua mão\n"
        "9. Se você tiver um Coringa e perder, a maldição será aleatória\n"
        "10. São 5 rodadas iniciais, podendo chegar a 10 se todos concordarem\n"
        "11. Fazer exatamente 21 pontos vale 2 pontos na rodada\n"
        "12. Vencer uma rodada normalmente vale 1 ponto\n"
        "⚠️ Jogue por sua conta e risco..."
    )

def main():
    print('Iniciando bot...')
    app = Application.builder().token(TOKEN).build()
    
    #comandos
    app.add_handler(CommandHandler('start', start_command))
    app.add_handler(CommandHandler('create_blackjack', create_blackjack_command))
    app.add_handler(CommandHandler('join', join_command))
    app.add_handler(CommandHandler('start_game', start_game_command))
    app.add_handler(CommandHandler('hit', hit_command))
    app.add_handler(CommandHandler('stand', stand_command))
    app.add_handler(CommandHandler('leave', leave_command))
    app.add_handler(CommandHandler('continue', continue_command))
    app.add_handler(CommandHandler('end', end_command))
    app.add_handler(CommandHandler('kill', kill_command))
    app.add_handler(CommandHandler('rules', rules_command))
    
    print('Bot iniciado!')
    app.run_polling(poll_interval=1)

if __name__ == '__main__':
    main()

