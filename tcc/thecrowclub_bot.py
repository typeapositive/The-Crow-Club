from typing import Final
from telegram import Update
from telegram.error import NetworkError, RetryAfter, TimedOut
from telegram.ext import Application, ChatMemberHandler, CommandHandler, MessageHandler, filters, ContextTypes
import asyncio
import html
import json
import random
from pathlib import Path
from blackjack_game import BlackjackGame, Card

INITIAL_COINS = 10
INITIAL_DEALER_COINS = 1000
DIRTHANDS_USER_ID = 5085147921
DIRTHANDS_INITIAL_COINS = 1004
BLACKJACK_LOSS_COINS = 3
MIN_LOAN_COINS = 3
MAX_LOAN_COINS = 12
BALANCES_FILE = Path(__file__).with_name("player_balances.json")
KNOWN_USERS_FILE = Path(__file__).with_name("known_users.json")
MONEY_LOSS_CURSES = {("Ouros", "2"), ("Ouros", "3"), ("Ouros", "4"), ("Ouros", "J"), ("Ouros", "K")}
VANISHING_MONEY_CURSES = {("Ouros", "2")}
GOLD_BONUS_CURSES = {("Ouros", "5")}
INCOMPATIBLE_CURSES = {
    ("Paus", "4"): {("Espadas", "Q")},
    ("Espadas", "Q"): {("Paus", "4")},
}
DEFAULT_CURSE_WEIGHT = 10
MONEY_LOSS_CURSE_WEIGHT = 3
VANISHING_MONEY_CURSE_WEIGHT = 1
GOLD_BONUS_CURSE_WEIGHT = 0.5
GOLD_BONUS_COINS = 20
ADMIN_USERNAMES = {"dirthands"}

player_balances = {}
dealer_balances = {}
player_debts = {}
known_users = {}

def load_economy():
    if not BALANCES_FILE.exists():
        return {}, {}, {}

    try:
        with BALANCES_FILE.open("r", encoding="utf-8") as file:
            data = json.load(file)
    except (json.JSONDecodeError, OSError):
        return {}, {}, {}

    if "players" in data or "dealers" in data or "debts" in data:
        players = data.get("players", {})
        dealers = data.get("dealers", {})
        debts = data.get("debts", {})
        return (
            {str(user_id): int(coins) for user_id, coins in players.items()},
            {str(chat_id): int(coins) for chat_id, coins in dealers.items()},
            {str(user_id): int(coins) for user_id, coins in debts.items()},
        )

    return {str(user_id): int(coins) for user_id, coins in data.items()}, {}, {}

def load_known_users():
    if not KNOWN_USERS_FILE.exists():
        return {}

    try:
        with KNOWN_USERS_FILE.open("r", encoding="utf-8") as file:
            data = json.load(file)
    except (json.JSONDecodeError, OSError):
        return {}

    users = {}

    # Legacy flat format: ignore for group-scoped lookups.
    if data and all(isinstance(value, dict) and "user_id" in value for value in data.values()):
        return {}

    for chat_id, chat_users in data.items():
        if not isinstance(chat_users, dict):
            continue

        users[str(chat_id)] = {}
        for username, user_data in chat_users.items():
            if not isinstance(user_data, dict):
                continue
            user_id = user_data.get("user_id")
            if user_id is None:
                continue
            users[str(chat_id)][username.lower()] = {
                "user_id": int(user_id),
                "first_name": str(user_data.get("first_name", username)),
            }

    return users

def save_economy():
    with BALANCES_FILE.open("w", encoding="utf-8") as file:
        json.dump(
            {
                "players": player_balances,
                "dealers": dealer_balances,
                "debts": player_debts,
            },
            file,
            ensure_ascii=False,
            indent=2,
        )

def save_known_users():
    with KNOWN_USERS_FILE.open("w", encoding="utf-8") as file:
        json.dump(known_users, file, ensure_ascii=False, indent=2)

def register_known_user(chat_id, user):
    if chat_id is None or not user or not user.username:
        return

    chat_key = str(chat_id)
    known_users.setdefault(chat_key, {})
    known_users[chat_key][user.username.lower()] = {
        "user_id": int(user.id),
        "first_name": user.first_name,
    }
    save_known_users()

def get_player_balance(user_id):
    key = str(user_id)
    if key not in player_balances:
        player_balances[key] = (
            DIRTHANDS_INITIAL_COINS
            if int(user_id) == DIRTHANDS_USER_ID
            else INITIAL_COINS
        )
        save_economy()
    return player_balances[key]

def has_vanishing_money_curse(user_id):
    _, session = find_user_session(user_id)
    if session is None:
        return False

    player = session.players.get(user_id)
    return player is not None and player.get("vanishing_money", False)

def get_dealer_balance(chat_id):
    key = str(chat_id)
    if key not in dealer_balances:
        dealer_balances[key] = INITIAL_DEALER_COINS
        save_economy()
    return dealer_balances[key]

def get_player_debt(user_id):
    return player_debts.get(str(user_id), 0)

def change_player_balance(user_id, amount):
    key = str(user_id)
    current_balance = get_player_balance(user_id)
    if amount > 0 and has_vanishing_money_curse(user_id):
        return current_balance

    player_balances[key] = max(0, current_balance + amount)
    save_economy()
    return player_balances[key]

def receive_player_coins(user_id, amount):
    key = str(user_id)
    get_player_balance(user_id)

    if amount <= 0:
        return 0
    if has_vanishing_money_curse(user_id):
        return 0

    player_balances[key] += amount
    save_economy()
    return amount

def change_dealer_balance(chat_id, amount):
    key = str(chat_id)
    dealer_balances[key] = max(0, get_dealer_balance(chat_id) + amount)
    save_economy()
    return dealer_balances[key]

def lend_from_dealer(chat_id, user_id, amount):
    dealer_key = str(DIRTHANDS_USER_ID)
    user_key = str(user_id)
    get_player_balance(DIRTHANDS_USER_ID)
    get_player_balance(user_id)

    if player_balances[dealer_key] < amount:
        return 0

    loan = amount
    player_balances[dealer_key] -= loan
    if not has_vanishing_money_curse(user_id):
        player_balances[user_key] += loan
    player_debts[user_key] = get_player_debt(user_id) + loan
    save_economy()
    return loan

def pay_debt_to_dealer(chat_id, user_id, amount):
    dealer_key = str(DIRTHANDS_USER_ID)
    user_key = str(user_id)
    debt = get_player_debt(user_id)
    balance = get_player_balance(user_id)
    get_player_balance(DIRTHANDS_USER_ID)
    payment = min(amount, debt, balance)

    if payment <= 0:
        return 0

    player_balances[user_key] = balance - payment
    player_balances[dealer_key] += payment
    remaining_debt = debt - payment

    if remaining_debt > 0:
        player_debts[user_key] = remaining_debt
    else:
        player_debts.pop(user_key, None)

    save_economy()
    return payment

def transfer_coins_to_winners(winner_ids, loser_ids):
    for winner_id in winner_ids:
        get_player_balance(winner_id)

    transfers = {}
    totals_received = {winner_id: 0 for winner_id in winner_ids}
    for loser_id in loser_ids:
        loser_key = str(loser_id)
        loser_balance = get_player_balance(loser_id)
        transferred = min(BLACKJACK_LOSS_COINS, loser_balance)
        share_base, remainder = divmod(transferred, len(winner_ids))

        player_balances[loser_key] = loser_balance - transferred
        transfers[loser_id] = {}
        for index, winner_id in enumerate(winner_ids):
            share = share_base + (1 if index < remainder else 0)
            if share <= 0:
                continue
            transfers[loser_id][winner_id] = share
            if not has_vanishing_money_curse(winner_id):
                player_balances[str(winner_id)] += share
                totals_received[winner_id] += share

    save_economy()
    return transfers, totals_received

def transfer_coins_to_winner(winner_id, loser_ids):
    transfers, totals_received = transfer_coins_to_winners([winner_id], loser_ids)
    return (
        {loser_id: sum(winner_amounts.values()) for loser_id, winner_amounts in transfers.items()},
        totals_received.get(winner_id, 0),
    )

def transfer_player_to_dealer(chat_id, user_id, amount):
    user_key = str(user_id)
    dealer_key = str(chat_id)
    available = get_player_balance(user_id)
    transferred = min(amount, available)
    player_balances[user_key] = available - transferred
    dealer_balances[dealer_key] = get_dealer_balance(chat_id) + transferred
    save_economy()
    return transferred

def transfer_player_to_player(from_user_id, to_user_id, amount):
    from_key = str(from_user_id)
    available = get_player_balance(from_user_id)
    transferred = min(amount, available)
    player_balances[from_key] = available - transferred
    save_economy()
    receive_player_coins(to_user_id, transferred)
    return transferred

def refund_player_transfer(from_user_id, to_user_id, amount):
    from_key = str(from_user_id)
    to_key = str(to_user_id)
    get_player_balance(from_user_id)
    to_balance = get_player_balance(to_user_id)

    if not has_vanishing_money_curse(from_user_id):
        player_balances[from_key] += amount
    player_balances[to_key] = max(0, to_balance - amount)
    save_economy()
    return amount

def remove_player_coins(user_id, amount):
    user_key = str(user_id)
    available = get_player_balance(user_id)
    removed = min(amount, available)
    player_balances[user_key] = available - removed
    save_economy()
    return removed

async def safe_send_message(context, chat_id, text, **kwargs):
    for attempt in range(2):
        try:
            return await context.bot.send_message(chat_id, text, **kwargs)
        except RetryAfter as error:
            if attempt == 0:
                await asyncio.sleep(error.retry_after + 1)
                continue
            print(f"Falha ao enviar mensagem para {chat_id}: flood control.")
            return None
        except (TimedOut, NetworkError):
            if attempt == 0:
                await asyncio.sleep(2)
                continue
            print(f"Falha ao enviar mensagem para {chat_id}: timeout/rede.")
            return None

def mention_user(user):
    return f'<a href="tg://user?id={user.id}">{html.escape(user.first_name)}</a>'

def mention_known_user(user_id, first_name):
    return f'<a href="tg://user?id={user_id}">{html.escape(first_name)}</a>'

def is_admin_user(user):
    return bool(user.username and user.username.lower() in ADMIN_USERNAMES)

def can_control_table(session, user):
    return user.id == session.host_id or is_admin_user(user)

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

def create_player_state():
    return {
        "hand": [],
        "total": 0,
        "stand": False,
        "message_id": None,
        "curses": [],
        "blinded": False,
        "last_round_curse": None,
        "last_round_money_curse_message": None,
        "curse_transfers": [],
        "vanishing_money": False,
    }

def get_curse_weight(card):
    curse_id = (card.suit, card.value)
    if curse_id in GOLD_BONUS_CURSES:
        return GOLD_BONUS_CURSE_WEIGHT
    if curse_id in VANISHING_MONEY_CURSES:
        return VANISHING_MONEY_CURSE_WEIGHT
    if curse_id in MONEY_LOSS_CURSES:
        return MONEY_LOSS_CURSE_WEIGHT
    return DEFAULT_CURSE_WEIGHT

def get_curse_id(card):
    return (card.suit, card.value)

def is_compatible_curse(player, curse_card):
    curse_id = get_curse_id(curse_card)
    blocked_curses = {
        blocked_curse
        for active_curse in player["curses"]
        for blocked_curse in INCOMPATIBLE_CURSES.get(get_curse_id(active_curse), set())
    }
    return curse_id not in blocked_curses

def choose_curse_card(cards, player, session=None):
    used_curse_ids = session.used_curse_ids if session is not None else set()
    compatible_cards = [
        card
        for card in cards
        if get_curse_id(card) not in used_curse_ids and is_compatible_curse(player, card)
    ]
    if not compatible_cards:
        return None
    return random.choices(
        compatible_cards,
        weights=[get_curse_weight(card) for card in compatible_cards],
        k=1,
    )[0]

def apply_curse_to_player(player, curse_card, session=None):
    player["curses"].append(curse_card)
    player["last_round_curse"] = curse_card
    if session is not None:
        session.used_curse_ids.add(get_curse_id(curse_card))

    if curse_card.value == "7" and curse_card.suit == "Paus":
        player["blinded"] = True
    if (curse_card.suit, curse_card.value) in VANISHING_MONEY_CURSES:
        player["vanishing_money"] = True

async def apply_immediate_curse_effects(chat_id, session, cursed_player_id, curse_card, context):
    if curse_card.suit != "Ouros" or curse_card.value not in ["2", "3", "5"]:
        return None

    if curse_card.value == "2":
        cursed_user = await context.bot.get_chat_member(chat_id, cursed_player_id)
        current_balance = get_player_balance(cursed_player_id)
        amount = remove_player_coins(cursed_player_id, current_balance)
        return (
            f"{mention_user(cursed_user.user)} perdeu {amount} moeda(s). "
            "Qualquer moeda que entrar no bolso também desaparecerá até a maldição terminar."
        )

    if curse_card.value == "5":
        cursed_user = await context.bot.get_chat_member(chat_id, cursed_player_id)
        received = receive_player_coins(cursed_player_id, GOLD_BONUS_COINS)
        if received <= 0:
            return (
                f"{mention_user(cursed_user.user)} encontrou {GOLD_BONUS_COINS} moeda(s), "
                "mas elas desapareceram antes de ficar no bolso."
            )
        return (
            f"{mention_user(cursed_user.user)} recebeu {received} moeda(s) "
            "pelo 5 de Ouros."
        )

    adversaries = [player_id for player_id in session.players.keys() if player_id != cursed_player_id]
    if not adversaries:
        return None

    cursed_user = await context.bot.get_chat_member(chat_id, cursed_player_id)
    recipient_id = adversaries[0] if len(adversaries) == 1 else random.choice(adversaries)
    recipient = await context.bot.get_chat_member(chat_id, recipient_id)
    current_balance = get_player_balance(cursed_player_id)
    amount = transfer_player_to_player(cursed_player_id, recipient_id, current_balance)

    if amount <= 0:
        return (
            f"{mention_user(cursed_user.user)} recebeu o 3 de Ouros, "
            "mas não tinha moedas para transferir."
        )

    session.players[cursed_player_id]["curse_transfers"].append(
        {
            "from": cursed_player_id,
            "to": recipient_id,
            "amount": amount,
            "curse": "3 de Ouros",
            "refunded": False,
        }
    )

    return (
        f"{mention_user(cursed_user.user)} perdeu {amount} moeda(s) para "
        f"{mention_user(recipient.user)} por causa do 3 de Ouros."
    )

async def auto_resolve_blinded_player(chat_id, session, player_id, context):
    player = session.players[player_id]
    game = session.game
    num_cards = random.randint(2, 5)
    player["hand"] = [game._draw_card() for _ in range(num_cards)]
    player["total"] = calculate_blackjack_score(player["hand"])
    player["stand"] = True
    player["last_round_curse"] = None
    player["last_round_money_curse_message"] = None

    if player["total"] > 21:
        if any(card.value == "Joker" for card in player["hand"]):
            curse_card = choose_curse_card(game._create_deck(), player, session)
        else:
            curse_card = choose_curse_card(player["hand"], player, session)
            if curse_card is None:
                curse_card = choose_curse_card(game._create_deck(), player, session)
        apply_curse_to_player(player, curse_card, session)
        player["last_round_money_curse_message"] = await apply_immediate_curse_effects(
            chat_id,
            session,
            player_id,
            curse_card,
            context,
        )

def is_player_broke_in_active_game(user_id):
    chat_id, session = find_user_session(user_id)
    return session is not None and session.started and get_player_balance(user_id) <= 0

def get_loan_chat_id(message_chat_id, user_id):
    active_chat_id, session = find_user_session(user_id)
    if session is not None and session.started:
        return active_chat_id
    return message_chat_id

async def apply_money_curse(chat_id, session, cursed_player_id, curse_card, context):
    if curse_card.suit != "Ouros":
        return None
    if curse_card.value in ["2", "3"]:
        return None

    cursed_user = await context.bot.get_chat_member(chat_id, cursed_player_id)
    cursed_name = mention_user(cursed_user.user)
    current_balance = get_player_balance(cursed_player_id)

    if curse_card.value in ["2", "K"]:
        amount = transfer_player_to_dealer(chat_id, cursed_player_id, current_balance)
        return (
            f"- {cursed_name} perdeu {amount} moeda(s) para Kaz Brekker "
            f"por causa do {curse_card.value} de Ouros."
        )

    if curse_card.value == "4":
        amount = (current_balance + 1) // 2
        removed = remove_player_coins(cursed_player_id, amount)
        return (
            f"- {cursed_name} perdeu {removed} moeda(s): "
            "o ouro foi diminuido pela metade por causa do 4 de Ouros."
        )

    if curse_card.value == "J":
        amount = remove_player_coins(cursed_player_id, current_balance)
        return (
            f"- {cursed_name} perdeu {amount} moeda(s) para alguém fora da mesa "
            "por causa do J de Ouros."
        )

    return None

async def apply_final_money_curses(chat_id, session, cursed_player_id, context):
    money_messages = []
    for curse_card in session.players[cursed_player_id]["curses"]:
        message = await apply_money_curse(chat_id, session, cursed_player_id, curse_card, context)
        if message:
            money_messages.append(message)
    return money_messages

async def refund_absolved_curse_transfers(chat_id, session, absolved_player_ids, context):
    refund_messages = []

    for player_id in absolved_player_ids:
        player = session.players[player_id]
        for transfer in player["curse_transfers"]:
            if transfer["refunded"]:
                continue

            refund_player_transfer(player_id, transfer["to"], transfer["amount"])
            transfer["refunded"] = True

            cursed_user = await context.bot.get_chat_member(chat_id, player_id)
            recipient = await context.bot.get_chat_member(chat_id, transfer["to"])
            refund_messages.append(
                f"- {mention_user(cursed_user.user)} recebeu de volta {transfer['amount']} moeda(s) "
                f"que tinham ido para {mention_user(recipient.user)} pelo {html.escape(transfer['curse'])}."
            )

    return refund_messages

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
        self.used_curse_ids = set()

active_sessions = {}  # chat_id: GameSession
player_balances, dealer_balances, player_debts = load_economy()
known_users = load_known_users()

async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    get_dealer_balance(update.message.chat_id)
    await update.message.reply_text(
        "Bem-vindo ao Clube do Corvo.\n\n"
        "Aqui, os jogos têm um preço além das fichas.\n"
        "Comandos disponíveis:\n"
        "/create_blackjack - Cria uma nova mesa de Blackjack\n"
        "/join - Entra na mesa atual\n"
        "/start_game - Inicia o jogo (apenas para o criador)\n"
        "/hit - Pede mais uma carta\n"
        "/stand - Mantém suas cartas\n"
        "/saldo - Mostra quantas moedas você tem\n"
        "/doar @usuário quantia - Doa moedas para outro jogador da mesa\n"
        "/pedir - Pede 3 a 12 moedas emprestadas ao Mãos Sujas\n"
        "/pay - Paga sua dívida com o Mãos Sujas\n"
        "/kick @usuário - Expulsa alguém da mesa (apenas @dirthands)\n"
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
            "As cartas em sua mão se recusam a deixar você ir. Você não pode deixar o jogo até o final da partida."
        )
        return
        
    session.players.pop(user_id, None)
    session.scores.pop(user_id, None)
    await update.message.reply_text("Você saiu da mesa. Sorte sua que o jogo ainda não havia começado...")

async def balance_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.message.chat_id
    user_id = update.message.from_user.id
    balance = get_player_balance(user_id)
    debt = get_player_debt(user_id)
    dealer_balance = get_player_balance(DIRTHANDS_USER_ID)
    await update.message.reply_text(
        f"Você tem {balance} moeda(s).\n"
        f"Dívida com o Mãos Sujas: {debt} moeda(s).\n"
        f"Mãos Sujas tem {dealer_balance} moeda(s)."
    )

async def find_session_player_by_username(chat_id, session, username, context):
    target_username = username.removeprefix("@").lower()
    for player_id in session.players.keys():
        member = await context.bot.get_chat_member(chat_id, player_id)
        register_known_user(chat_id, member.user)
        member_username = member.user.username
        if member_username and member_username.lower() == target_username:
            return player_id, member.user
    return None, None

def find_known_user_by_username(chat_id, username):
    chat_key = str(chat_id)
    target_username = username.removeprefix("@").lower()
    return known_users.get(chat_key, {}).get(target_username)

def parse_command_args(message_text):
    if not message_text:
        return []

    parts = message_text.strip().split()
    if not parts:
        return []

    return parts[1:]

async def register_known_user_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message is None:
        return

    register_known_user(update.message.chat_id, update.message.from_user)

async def donate_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.message.chat_id
    donor_id = update.message.from_user.id
    donor_balance = get_player_balance(donor_id)
    donate_args = context.args or parse_command_args(update.message.text)
    register_known_user(chat_id, update.message.from_user)

    if len(donate_args) != 2 or not donate_args[0].startswith("@"):
        await update.message.reply_text(
            "Use /doar @usuário quantia. Exemplo: /doar @rodapunk 3\n"
            f"Você tem {donor_balance} moeda(s)."
        )
        return

    session = active_sessions.get(chat_id)
    if session is not None and donor_id not in session.players:
        await update.message.reply_text(
            "Você precisa estar na mesa para doar moedas a outro jogador.\n"
            f"Você tem {donor_balance} moeda(s)."
        )
        return

    try:
        amount = int(donate_args[1])
    except ValueError:
        await update.message.reply_text(
            "A quantia precisa ser um número inteiro.\n"
            f"Você tem {donor_balance} moeda(s)."
        )
        return

    if amount <= 0:
        await update.message.reply_text(
            "A doação precisa ser maior que zero.\n"
            f"Você tem {donor_balance} moeda(s)."
        )
        return

    if amount > donor_balance:
        await update.message.reply_text(
            f"Você tem {donor_balance} moeda(s) e não pode doar {amount}."
        )
        return

    recipient_id = None
    recipient = None

    if session is not None:
        recipient_id, recipient = await find_session_player_by_username(
            chat_id,
            session,
            donate_args[0],
            context,
        )

    if recipient_id is None:
        known_user = find_known_user_by_username(chat_id, donate_args[0])
        if known_user is not None:
            recipient_id = known_user["user_id"]
            recipient = None

    if recipient_id is None:
        await update.message.reply_text(
            "Não encontrei esse @ para doar moedas.\n"
            f"Você tem {donor_balance} moeda(s)."
        )
        return

    if recipient_id == donor_id:
        await update.message.reply_text(
            "Você não pode doar moedas para si mesmo.\n"
            f"Você tem {donor_balance} moeda(s)."
        )
        return

    recipient_money_vanishes = has_vanishing_money_curse(recipient_id)
    donated = transfer_player_to_player(donor_id, recipient_id, amount)
    donor_balance = get_player_balance(donor_id)
    recipient_balance = get_player_balance(recipient_id)
    recipient_label = (
        mention_user(recipient)
        if recipient is not None
        else mention_known_user(
            recipient_id,
            known_users[str(chat_id)][donate_args[0].removeprefix("@").lower()]["first_name"],
        )
    )

    if recipient_money_vanishes:
        await update.message.reply_text(
            f"Você doou {donated} moeda(s) para {recipient_label}, mas elas desapareceram.\n"
            f"Você agora tem {donor_balance} moeda(s).",
            parse_mode="HTML",
        )
        return

    await update.message.reply_text(
        f"Você doou {donated} moeda(s) para {recipient_label}.\n"
        f"Você agora tem {donor_balance} moeda(s).\n"
        f"{recipient_label} agora tem {recipient_balance} moeda(s).",
        parse_mode="HTML",
    )

async def kick_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.message.chat_id

    if not is_admin_user(update.message.from_user):
        await update.message.reply_text("Só @dirthands pode expulsar alguém da mesa.")
        return

    kick_args = context.args or parse_command_args(update.message.text)
    if len(kick_args) != 1 or not kick_args[0].startswith("@"):
        await update.message.reply_text("Use /kick @usuário.")
        return

    session = active_sessions.get(chat_id)
    if session is None:
        await update.message.reply_text("Não há mesa ativa neste chat.")
        return

    target_id, target_user = await find_session_player_by_username(
        chat_id,
        session,
        kick_args[0],
        context,
    )

    if target_id is None:
        await update.message.reply_text("Não encontrei esse @ na mesa.")
        return

    session.players.pop(target_id, None)
    session.scores.pop(target_id, None)
    session.votes_continue.discard(target_id)
    session.votes_end.discard(target_id)

    await update.message.reply_text(
        f"{mention_user(target_user)} foi expulso da mesa por @dirthands.",
        parse_mode="HTML",
    )

    if session.started and len(session.players) < session.min_players:
        del active_sessions[chat_id]
        await update.message.reply_text("A partida foi encerrada porque restaram menos de 2 jogadores.")

async def bot_chat_member_update(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat = update.my_chat_member.chat
    new_status = update.my_chat_member.new_chat_member.status

    if chat.type in ["group", "supergroup"] and new_status in ["member", "administrator"]:
        get_dealer_balance(chat.id)

async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE):
    if isinstance(context.error, RetryAfter):
        print(f"Flood control do Telegram ignorado; tente novamente em {context.error.retry_after}s.")
        return

    if isinstance(context.error, (TimedOut, NetworkError)):
        print("Erro de rede/timeout do Telegram ignorado; o bot continua rodando.")
        return

    raise context.error

async def ask_loan_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id
    chat_id = get_loan_chat_id(update.message.chat_id, user_id)
    get_dealer_balance(chat_id)
    get_player_balance(user_id)

    if context.args:
        try:
            amount = int(context.args[0])
        except ValueError:
            await update.message.reply_text("Diga um número entre 3 e 12. Exemplo: /pedir 6")
            return

        if amount < MIN_LOAN_COINS or amount > MAX_LOAN_COINS:
            await update.message.reply_text("Mãos Sujas só empresta valores entre 3 e 12 moedas.")
            return

        loan = lend_from_dealer(chat_id, user_id, amount)
        if loan <= 0:
            await update.message.reply_text("Mãos Sujas não tem moedas suficientes para emprestar agora.")
            return

        await update.message.reply_text(
            f"Mãos Sujas emprestou {loan} moeda(s).\n"
            f"Sua dívida com o Mãos Sujas: {get_player_debt(user_id)} moeda(s)."
        )
        if has_vanishing_money_curse(user_id):
            await update.message.reply_text("As moedas desapareceram antes de ficarem no seu bolso.")
        return

    context.user_data["awaiting_loan_amount"] = True
    await update.message.reply_text("Quanto você vai pedir ao Mãos Sujas? Envie um valor de 3 a 12.")

async def loan_amount_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.user_data.get("awaiting_loan_amount"):
        return

    context.user_data["awaiting_loan_amount"] = False
    text = update.message.text.strip()
    try:
        amount = int(text)
    except ValueError:
        await update.message.reply_text("Mãos Sujas esperava um número. Use /pedir de novo e escolha um valor de 3 a 12.")
        return

    if amount < MIN_LOAN_COINS or amount > MAX_LOAN_COINS:
        await update.message.reply_text("Mãos Sujas só empresta valores entre 3 e 12 moedas. Use /pedir de novo.")
        return

    user_id = update.message.from_user.id
    chat_id = get_loan_chat_id(update.message.chat_id, user_id)
    loan = lend_from_dealer(chat_id, user_id, amount)
    if loan <= 0:
        await update.message.reply_text("Mãos Sujas não tem moedas suficientes para emprestar agora.")
        return

    await update.message.reply_text(
        f"Mãos Sujas emprestou {loan} moeda(s).\n"
        f"Sua dívida com o Mãos Sujas: {get_player_debt(user_id)} moeda(s)."
    )
    if has_vanishing_money_curse(user_id):
        await update.message.reply_text("As moedas desapareceram antes de ficarem no seu bolso.")

async def pay_debt_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id
    chat_id = get_loan_chat_id(update.message.chat_id, user_id)
    debt = get_player_debt(user_id)
    balance = get_player_balance(user_id)

    if debt <= 0:
        await update.message.reply_text("Você não deve nada ao Mãos Sujas.")
        return

    if balance <= 0:
        await update.message.reply_text("Você não tem moedas para pagar o Mãos Sujas agora.")
        return

    if context.args:
        arg = context.args[0].lower()
        if arg in ["all", "tudo", "todas"]:
            amount = debt
        else:
            try:
                amount = int(arg)
            except ValueError:
                await update.message.reply_text("Use /pay, /pay tudo ou /pay seguido de um número.")
                return

            if amount <= 0:
                await update.message.reply_text("O pagamento precisa ser maior que zero.")
                return
    else:
        amount = debt

    paid = pay_debt_to_dealer(chat_id, user_id, amount)
    remaining_debt = get_player_debt(user_id)

    await update.message.reply_text(
        f"Você pagou {paid} moeda(s) ao Mãos Sujas.\n"
        f"Dívida restante: {remaining_debt} moeda(s)."
    )

async def create_blackjack_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.message.chat_id
    user_id = update.message.from_user.id
    get_dealer_balance(chat_id)
    admin_user = is_admin_user(update.message.from_user)

    if not admin_user and get_player_balance(user_id) <= 0:
        await update.message.reply_text(
            "Você está sem moedas e não pode criar uma mesa assim.\n"
            "Antes de criar uma mesa, peça moedas com /pedir."
        )
        return
    
    if chat_id in active_sessions:
        await update.message.reply_text("Já existe uma mesa ativa neste chat.")
        return
        
    session = GameSession(user_id)
    if not admin_user:
        session.players[user_id] = create_player_state()
        session.scores[user_id] = 0
        get_player_balance(user_id)
    active_sessions[chat_id] = session
    
    await update.message.reply_text(
        "Mesa de Blackjack criada!\n"
        "Outros jogadores podem entrar usando /join@TheCrowClub_bot\n"
        "São necessários no mínimo 2 jogadores para começar.\n"
        "Quando todos estiverem prontos, use /start_game@TheCrowClub_bot"
    )

async def join_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.message.chat_id
    user_id = update.message.from_user.id
    get_dealer_balance(chat_id)
    
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

    if get_player_balance(user_id) <= 0:
        await update.message.reply_text(
            "Você está sem moedas e não pode entrar na mesa assim.\n"
            "Peça moedas com /pedir antes de entrar na mesa."
        )
        return
        
    session.players[user_id] = create_player_state()
    session.scores[user_id] = 0
    await update.message.reply_text(
        f"Jogador {mention_user(update.message.from_user)} entrou na mesa!",
        parse_mode="HTML",
    )

async def start_game_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.message.chat_id
    user_id = update.message.from_user.id
    
    if chat_id not in active_sessions:
        await update.message.reply_text("Não há mesa ativa neste chat.")
        return
        
    session = active_sessions[chat_id]
    
    if not can_control_table(session, update.message.from_user):
        await update.message.reply_text("Apenas o criador da mesa pode iniciar o jogo.")
        return
        
    if session.started:
        await update.message.reply_text("O jogo já começou.")
        return

    if len(session.players) < session.min_players:
        await update.message.reply_text("São necessários no mínimo 2 jogadores para começar.")
        return

    broke_players = []
    for player_id in session.players.keys():
        if get_player_balance(player_id) <= 0:
            member = await context.bot.get_chat_member(chat_id, player_id)
            broke_players.append(mention_user(member.user))

    if broke_players:
        await update.message.reply_text(
            "A mesa não pode começar enquanto houver jogador sem moedas.\n"
            f"Sem saldo: {', '.join(broke_players)}.\n"
            "Quem estiver sem moedas deve usar /pedir.",
            parse_mode="HTML",
        )
        return
        
    session.started = True

    # apresentação dos jogadores e dealer
    players_list = []

    for player_id in session.players.keys():
        member = await context.bot.get_chat_member(chat_id, player_id)
        players_list.append(f"• {mention_user(member.user)}")

    players_text = "\n".join(players_list)

    await update.message.reply_text(
        "Bem-vindos ao Crow Club!\n\n"
        "Seu dealer hoje será Kaz Brekker, o proprietário do Clube do Corvo.\n"
        "Jogadores na mesa:\n"
        f"{players_text}\n\n"
        f"Iniciando rodada {session.current_round} de {session.max_rounds}!\n"
        "Pegue suas cartas iniciais: /hit@TheCrowClub_bot",
        parse_mode="HTML",
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

        round_summary = f"Resultados da rodada {session.current_round}:"
        player_summaries = []
        for player_id, data in session.players.items():
            user = await context.bot.get_chat_member(chat_id, player_id)
            player_name = mention_user(user.user)
            cards_text = html.escape(", ".join([f"{card.value} de {card.suit}" for card in data["hand"]]))

            if data["total"] > 21:
                status = "Estourou"
            elif player_id in session.round_winners:
                status = "Venceu"
            else:
                status = "Perdeu"

            player_summary = f"- {player_name}: {cards_text} (Total: {data['total']}) - {status}"

            if data["last_round_curse"] is not None:
                curse_card = data["last_round_curse"]
                player_summary += (
                    f"\n\n  Maldição: {curse_card.value} de {curse_card.suit}"
                    f"\n  Efeito: {html.escape(curse_card.curse)}"
                )
                if data["last_round_money_curse_message"]:
                    player_summary += f"\n  Moedas: {html.escape(data['last_round_money_curse_message'])}"

            player_summaries.append(player_summary)

        round_summary += "\n\n" + "\n\n".join(player_summaries)
        await safe_send_message(context, chat_id, round_summary, parse_mode="HTML")

        if session.round_winners:
            winners_text = ""
            for winner_id in session.round_winners:
                user = await context.bot.get_chat_member(chat_id, winner_id)
                points = session.players[winner_id]["total"]
                winners_text += f"\n- {mention_user(user.user)} com {points} pontos!"

            scores_text = ""
            for pid, score in session.scores.items():
                user = await context.bot.get_chat_member(chat_id, pid)
                scores_text += f"\n- {mention_user(user.user)}: {score} pontos"

            await safe_send_message(
                context,
                chat_id,
                f"Fim da rodada {session.current_round}!\n"
                f"Vencedor(es):{winners_text}\n"
                "Pontuação atual:"
                + scores_text,
                parse_mode="HTML",
            )
        else:
            await safe_send_message(
                context,
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
                    await safe_send_message(
                        context,
                        chat_id,
                        "Temos um empate! O jogo continuará automaticamente até 10 rodadas para desempate!"
                    )
                    await start_new_round(chat_id, session, context)
                    return
                else:
                    await safe_send_message(
                        context,
                        chat_id,
                        "Fim das 5 rodadas iniciais!\nUse /continue para votar em mais 5 rodadas\nOu /end para encerrar o jogo"
                    )
            else:
                await end_game(chat_id, session, context)
        else:
            await start_new_round(chat_id, session, context)

async def start_new_round(chat_id, session, context):
    session.game = BlackjackGame()

    for player_id in list(session.players.keys()):
        session.players[player_id]["hand"] = []
        session.players[player_id]["total"] = 0
        session.players[player_id]["stand"] = False
        session.players[player_id]["message_id"] = None
        session.players[player_id]["last_round_curse"] = None
        session.players[player_id]["last_round_money_curse_message"] = None

    await safe_send_message(
        context,
        chat_id,
        f"Iniciando rodada {session.current_round} de {session.max_rounds}!\n"
        "Pegue suas cartas iniciais: /hit@TheCrowClub_bot"
    )

    for player_id, player in session.players.items():
        if player["blinded"]:
            await auto_resolve_blinded_player(chat_id, session, player_id, context)

    if all(player["stand"] for player in session.players.values()):
        await check_round_end(chat_id, session, context)

async def hit_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id

    chat_id, session = find_user_session(user_id)

    if session is None:
        await update.message.reply_text("Você não está participando de nenhum jogo ativo.")
        return

    if user_id not in session.players:
        await update.message.reply_text("Você não está participando deste jogo.")
        return

    if get_player_balance(user_id) <= 0:
        await update.message.reply_text(
            "Você está sem moedas no meio da partida. A saída é proibida.\n"
            "Peça de 3 a 12 moedas ao Mãos Sujas com /pedir."
        )
        return

    if session.players[user_id]["blinded"]:
        await update.message.reply_text("Você está cego pelo 7 de Paus e Kaz irá jogar por você até o fim da partida. Confie no seu dealer.")
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
        await safe_send_message(context, chat_id, f"{user.first_name} pegou uma carta.")
        await safe_send_message(context, user_id, private_message)
        await asyncio.sleep(2)
        await safe_send_message(context, chat_id, f"{user.first_name} finalizou a rodada.")
        await check_round_end(chat_id, session, context)
    elif total > 21:
        if any(card.value == "Joker" for card in player["hand"]):
            all_curses = session.game._create_deck()
            curse_card = choose_curse_card(all_curses, player, session)
        else:
            curse_card = choose_curse_card(player["hand"], player, session)
            if curse_card is None:
                curse_card = choose_curse_card(session.game._create_deck(), player, session)

        apply_curse_to_player(player, curse_card, session)
        money_curse_message = await apply_immediate_curse_effects(
            chat_id,
            session,
            user_id,
            curse_card,
            context,
        )
        player["last_round_money_curse_message"] = money_curse_message

        private_message = (
            f"Você ultrapassou 21 com {total} pontos!\n"
            f"A maldição recai sobre você através da carta:\n"
            f"{curse_card.value} de {curse_card.suit}\n"
            f"Sua punição será:\n"
            f"{curse_card.curse}"
        )
        if money_curse_message:
            private_message += f"\n\nMoedas: {money_curse_message}"
        await safe_send_message(context, chat_id, f"{user.first_name} pegou uma carta.")
        await safe_send_message(context, user_id, private_message)
        player["stand"] = True
        await asyncio.sleep(2)
        await safe_send_message(context, chat_id, f"{user.first_name} finalizou a rodada.")
        await check_round_end(chat_id, session, context)
    else:
        private_message += "Use /hit para mais uma carta ou /stand para manter"
        await safe_send_message(context, user_id, private_message)
        await safe_send_message(context, chat_id, f"{user.first_name} pegou uma carta.")

async def stand_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id

    chat_id, session = find_user_session(user_id)

    if session is None:
        await update.message.reply_text("Você não está participando de nenhum jogo ativo.")
        return

    if user_id not in session.players:
        await update.message.reply_text("Você não está participando deste jogo.")
        return

    if get_player_balance(user_id) <= 0:
        await update.message.reply_text(
            "Você está sem moedas no meio da partida. A saída é proibida.\n"
            "Peça de 3 a 12 moedas ao Mãos Sujas com /pedir."
        )
        return

    if session.players[user_id]["blinded"]:
        await update.message.reply_text("Você está cego pelo 7 de Paus e Kaz irá jogar por você até o fim da partida. Confie no seu dealer.")
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
    await safe_send_message(context, user_id, private_message)
    await safe_send_message(context, chat_id, f"{user.first_name} finalizou a rodada.")

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
    max_score = max(session.scores.values())
    min_score = min(session.scores.values())
    final_winners = [pid for pid, score in session.scores.items() if score == max_score]
    last_place_players = [pid for pid, score in session.scores.items() if score == min_score]
    final_message = "Fim do jogo!\n"

    if len(final_winners) == 1:
        final_winner_id = final_winners[0]
        losers = [player_id for player_id in session.players.keys() if player_id != final_winner_id]

        winner = await context.bot.get_chat_member(chat_id, final_winner_id)
        winner_name = mention_user(winner.user)
        transfers, total_received = transfer_coins_to_winner(final_winner_id, losers)

        final_message += f"Grande vencedor: {winner_name} com {max_score} pontos!\n"
        final_message += f"{winner_name} recebeu {total_received} moeda(s). Saldo atual: {get_player_balance(final_winner_id)} moeda(s)."

        if transfers:
            final_message += "\n\nTransferências:"
            for loser_id, amount in transfers.items():
                loser = await context.bot.get_chat_member(chat_id, loser_id)
                final_message += (
                    f"\n- {mention_user(loser.user)} perdeu {amount} moeda(s). "
                    f"Saldo atual: {get_player_balance(loser_id)} moeda(s)."
                )
    else:
        losers = [player_id for player_id in session.players.keys() if player_id not in final_winners]
        winners_names = [
            mention_user((await context.bot.get_chat_member(chat_id, winner_id)).user)
            for winner_id in final_winners
        ]
        transfers, totals_received = transfer_coins_to_winners(final_winners, losers)
        final_message += (
            f"Houve um empate entre: {', '.join(winners_names)}\n"
            f"Cada um com {max_score} pontos!\n"
            "O ouro foi dividido entre os primeiros lugares."
        )

        if totals_received:
            final_message += "\n\nRecebimentos:"
            for winner_id in final_winners:
                winner = await context.bot.get_chat_member(chat_id, winner_id)
                final_message += (
                    f"\n- {mention_user(winner.user)} recebeu "
                    f"{totals_received.get(winner_id, 0)} moeda(s). "
                    f"Saldo atual: {get_player_balance(winner_id)} moeda(s)."
                )

        if transfers:
            final_message += "\n\nTransferências:"
            for loser_id, winner_amounts in transfers.items():
                loser = await context.bot.get_chat_member(chat_id, loser_id)
                paid = sum(winner_amounts.values())
                final_message += (
                    f"\n- {mention_user(loser.user)} perdeu {paid} moeda(s). "
                    f"Saldo atual: {get_player_balance(loser_id)} moeda(s)."
                )

    final_message += "\n\nMaldições finais:"
    cursed_player_ids = last_place_players

    if len(cursed_player_ids) > 1:
        tied_names = [
            mention_user((await context.bot.get_chat_member(chat_id, player_id)).user)
            for player_id in cursed_player_ids
        ]
        final_message += (
            f"\n\nHouve empate no último lugar entre: {', '.join(tied_names)}."
            "\nTodos permanecem com suas maldições."
        )

    for cursed_player_id in cursed_player_ids:
        cursed_user = await context.bot.get_chat_member(chat_id, cursed_player_id)
        cursed_name = mention_user(cursed_user.user)
        curses = [f"- {html.escape(curse.curse)}" for curse in session.players[cursed_player_id]["curses"]]
        curse_hours = random.randint(1, 12)

        if curses:
            curses_text = "\n\n".join(curses)
            final_message += (
                f"\n\n{cursed_name} ficou em último lugar com {min_score} ponto(s) "
                f"e sofrerá por {curse_hours} horas:\n\n{curses_text}"
            )
        else:
            final_message += (
                f"\n\n{cursed_name} ficou em último lugar, "
                "mas não carregava maldições."
            )

        money_curse_messages = await apply_final_money_curses(chat_id, session, cursed_player_id, context)
        if money_curse_messages:
            final_message += "\n\nConsequências financeiras das maldições:"
            final_message += "\n" + "\n".join(money_curse_messages)
            final_message += f"\nKaz Brekker agora tem {get_dealer_balance(chat_id)} moeda(s)."

    absolved_names = [
        mention_user((await context.bot.get_chat_member(chat_id, player_id)).user)
        for player_id in session.players.keys()
        if player_id not in cursed_player_ids
    ]
    absolved_player_ids = [
        player_id
        for player_id in session.players.keys()
        if player_id not in cursed_player_ids
    ]

    if absolved_names:
        final_message += f"\n\nAbsolvidos: {', '.join(absolved_names)}."
        refund_messages = await refund_absolved_curse_transfers(
            chat_id,
            session,
            absolved_player_ids,
            context,
        )
        if refund_messages:
            final_message += "\n\nDevoluções do 3 de Ouros:"
            final_message += "\n" + "\n".join(refund_messages)
    else:
        final_message += "\n\nNinguém foi absolvido."

    await safe_send_message(context, chat_id, final_message, parse_mode="HTML")
    del active_sessions[chat_id]

async def kill_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.message.chat_id
    user_id = update.message.from_user.id
    
    if chat_id not in active_sessions:
        await update.message.reply_text("Não há jogo ativo neste chat.")
        return
        
    session = active_sessions[chat_id]
    
    if not can_control_table(session, update.message.from_user):
        await update.message.reply_text("Apenas o criador da mesa pode encerrar o jogo.")
        return

    del active_sessions[chat_id]
    await update.message.reply_text("O jogo foi encerrado pelo criador da mesa.")

async def rules_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "Regras do Blackjack:\n\n"
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
        "13. Cada jogador começa com 10 moedas persistentes\n"
        "14. Ao fim da partida, cada perdedor transfere até 3 moedas ao vencedor\n"
        "15. Apenas quem ficar sozinho em último lugar sofre as maldições finais\n"
        "16. Mãos Sujas tem 1004 moedas e é dele que saem os empréstimos de /pedir e entram os pagamentos de /pay\n"
        "17. Se ficar sem moedas, use /pedir para pegar de 3 a 12 moedas emprestadas\n"
        "18. Use /pay para pagar tudo que puder ou /pay 2 para pagar aos poucos\n"
        "19. Use /doar @usuário quantia para doar moedas a outro jogador da mesa\n"
        "20. Só @dirthands pode usar /kick @usuário para expulsar alguém da mesa\n"
        "Jogue por sua conta e risco..."
    )

def main():
    print('Iniciando bot...')
    app = (
        Application.builder()
        .token(TOKEN)
        .connect_timeout(30)
        .read_timeout(30)
        .write_timeout(30)
        .pool_timeout(30)
        .build()
    )
    
    #comandos
    app.add_handler(MessageHandler(filters.ALL, register_known_user_message), group=-1)
    app.add_handler(ChatMemberHandler(bot_chat_member_update, ChatMemberHandler.MY_CHAT_MEMBER))
    app.add_handler(CommandHandler('start', start_command))
    app.add_handler(CommandHandler('create_blackjack', create_blackjack_command))
    app.add_handler(CommandHandler('join', join_command))
    app.add_handler(CommandHandler('start_game', start_game_command))
    app.add_handler(CommandHandler('hit', hit_command))
    app.add_handler(CommandHandler('stand', stand_command))
    app.add_handler(CommandHandler('saldo', balance_command))
    app.add_handler(CommandHandler('doar', donate_command))
    app.add_handler(CommandHandler('pedir', ask_loan_command))
    app.add_handler(CommandHandler('pay', pay_debt_command))
    app.add_handler(CommandHandler('kick', kick_command))
    app.add_handler(CommandHandler('leave', leave_command))
    app.add_handler(CommandHandler('continue', continue_command))
    app.add_handler(CommandHandler('end', end_command))
    app.add_handler(CommandHandler('kill', kill_command))
    app.add_handler(CommandHandler('rules', rules_command))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, loan_amount_message))
    app.add_error_handler(error_handler)
    
    print('Bot iniciado!')
    app.run_polling(poll_interval=1)

if __name__ == '__main__':
    main()


