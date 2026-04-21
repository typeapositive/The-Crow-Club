import random
from typing import List, Tuple

class Card:
    def __init__(self, suit: str, value: str, curse: str):
        self.suit = suit
        self.value = value
        self.curse = curse

    def __str__(self) -> str:
        return f"{self.value} de {self.suit}"

class BlackjackGame:
    def __init__(self):
        self.deck = self._create_deck()
        self.player_hand: List[Card] = []
        self.dealer_hand: List[Card] = []
        self._shuffle_deck()

    def _create_deck(self) -> List[Card]:
        suits = ["Ouros", "Copas", "Espadas", "Paus"]
        values = ["2", "3", "4", "5", "6", "7", "8", "9", "10", "J", "Q", "K", "A"]
        
        # Dicionário de maldições para cada carta
        curses = {
            "A": {
                "Copas": "O sangue pulsa fora do ritmo. O coração pesa como chumbo. Você sente muita tristeza e seu passado assombra seus pensamentos.",
                "Espadas": "Uma lâmina invisível encosta na nuca. A dor é silenciosa, mas real. Não faça movimentos bruscos, ou ela cortará sua pele.",
                "Ouros": "Os dedos ardem ao tocar o ouro. Tudo que reluz te rejeita e queima a sua pele.",
                "Paus": "Sussurros ecoam ao redor. Eles sabem o que você fez. E o que você quer fazer."
            },
            "2": {
                "Copas": "Sua língua enrola. As palavras somem da sua mente como fumaça.",
                "Espadas": "Um corte fino se abre no braço. Você não viu de onde veio.",
                "Ouros": "As moedas vibram em seu bolso… e depois, desaparecem. Você perde todo o dinheiro que estava carregando. E todo dinheiro que entrar no seu bolso, desaparecerá até a maldição terminar.",
                "Paus": "Seu pulso treme. Você se sente obrigado a lançar um feitiço em algum de seus adversários."
            },
            "3": {
                "Copas": "Um calor febril sobe pelas veias. O mundo parece distante. Você sente um grande vazio existencial.",
                "Espadas": "Você ouve passos atrás de si. Ninguém está lá. Os passos não param e parecem mais altos que qualquer outra coisa, perseguindo você.",
                "Ouros": "Seu ouro canta um lamento. Ele não deseja mais ser seu. Seu dinheiro inteiro vai para um de seus adversários.",
                "Paus": "Sua mão se move sem comando. Algo assumiu o controle. Você perde o movimento da mão dominante e ela quer estapear qualquer um que se aproxima de você."
            },
            "4": {
                "Copas": "O ar ao seu redor congela. Os outros não parecem notar. Você está com muito, muito frio.",
                "Espadas": "Sente-se observado. Os olhos... eles não piscam. Você vê dois olhos em todo canto escuro que olhar. Eles são assustadores.",
                "Ouros": "Toque de Midas ao contrário. Todo ouro que você tocar, vai se transformar em pó.",
                "Paus": "Sua voz ecoa com atraso. Algo a repete em outro lugar. Você não consegue falar, mas pode gritar."
            },
            "5": {
                "Copas": "Uma memória esquecida ressurge. Você queria mantê-la enterrada. Ela está vívida demais e você tem alucinações visuais e auditivas com ela.",
                "Espadas": "O cheiro de ferro preenche o ar. Suas mãos estão cobertas de sangue. Tudo que você tocar, vai sangrar. Mas só você pode ver.",
                "Ouros": "O ouro pesa mais do que devia. Você carrega culpa com ele. Seus bolsos se enchem de ouro, mas cada vez que gastar, revive a sua pior memória.",
                "Paus": "Risos abafados se espalham pelas sombras. Estão rindo de você? Você sente uma paranoia profunda."
            },
            "6": {
                "Copas": "Bloody Mary. Superfícies espelhadas refletem uma mulher assustadora que se aproxima de você cada vez mais. Quando você desvia o olhar, ela volta do início. Quer descobrir o que acontece se não parar de olhar? ",
                "Espadas": "Algo arranha sua perna. Nada visível, mas sangra. A cada uma hora, essa mesma coisa arranha uma parte do seu corpo.",
                "Ouros": "Os números se embaralham diante dos seus olhos. Confusão. Você desaprende a contar.",
                "Paus": "Você precisa vencer em tudo. Se você falhar, receberá uma chicotada nas costas. O açoite é invisível, mas a dor é real."
            },
            "7": {
                "Copas": "O coração corre, descompassado. O medo chegou antes do motivo. Você se assusta com as pequenas coisas.",
                "Espadas": "Senescal da justiça. Você é severamente punido pela lâmina da justiça se mentir. Fale apenas a verdade.",
                "Ouros": "As moedas sussurram entre si. Qualquer dinheiro que você tiver consigo, sussurrará suas maiores inseguranças.",
                "Paus": "As sombras se alongam ao seu redor. Estão te envolvendo. Você fica cego."
            },
            "8": {
                "Copas": "Uma paixão proibida invade sua mente. Você se apaixona por um adversário.",
                "Espadas": "Uma lâmina paira acima da cabeça. Esperando cair. Ela pode cair a qualquer momento, então é melhor não tirar os olhos dela.",
                "Ouros": "Um brilho falso ofusca sua visão. Riqueza envenenada. Qualquer moeda que você olhar, brilhará ccomo o sol.",
                "Paus": "O tempo desacelera. Cada batida parece um século. Você só consegue falar em câmera lenta."
            },
            "9": {
                "Copas": "Um nome perdido sussurra em seus ouvidos. Você o conhecia? Alguém do seu passado volta para te assombrar.",
                "Espadas": "Seu braço pesa como pedra. Mal consegue movê-lo.",
                "Ouros": "O som de tilintar se torna insuportável. Ilusão ou aviso?",
                "Paus": "O chão vibra sob seus pés. Algo se aproxima por baixo. É difícil manter o equilíbrio."
            },
            "10": {
                "Copas": "O amor traiu. Sente-se vazio, como depois de um beijo esquecido.",
                "Espadas": "Seu sangue gela. Não por medo… por premonição. Algo está prestes a acontecer, mas você não sabe o quê. Isso lhe causa uma enorme ansiedade.",
                "Ouros": "O ouro da necromante. Você vê gente morta sempre que tocar em dinheiro.",
                "Paus": "Seus membros se movem por vontade própria. A dança da perdição. Você precisa dançar a cada 10 minutos enquanto estiver acordado."
            },
            "J": {
                "Copas": "Um rosto familiar aparece nos olhos de todos. Mas está morto. Seus adversários estão com uma aparência horrível de cadáver em decomposição. E cheiro...",
                "Espadas": "Retaliação. Você precisa punir um de seus adversários sempre que ele lhe irritar.",
                "Ouros": "As moedas pulam da sua bolsa. Elas escolheram outro dono. Pode estar com qualquer pessoa ao seu redor.",
                "Paus": "O morto-vivo. Toque é gelado como o de um vampiro. E você sente sede de sangue."
            },
            "Q": {
                "Copas": "Uma figura elegante encosta em seu ombro. Gélida. Invisível. Ela sussurra seus desejos mais profundos.",
                "Espadas": "Um feitiço se prende à sua língua. Você não fala, você sussurra.",
                "Ouros": "Ela sorri para você, com olhos feitos de rubis. Você não se move. Você paralisa por cinco minutos sempre que olhar nos olhos de alguém.",
                "Paus": "Sua pele formiga. As runas antigas despertam sob sua carne. Seu corpo inteiro está coçando."
            },
            "K": {
                "Copas": "Uma voz autoritária ordena: ceda. Você obedece, sem saber a quem. A próxima coisa que lhe pedirem, você é obrigado a aceitar.",
                "Espadas": "Seu peito dói — não por ataque, mas por vergonha profunda. Você agora fala gaguejando.",
                "Ouros": "O Rei exige tributo. Algo seu agora pertence a ele. Dê tudo o que você tem ao dealer. E se não tiver nada, dê o seu sangue.",
                "Paus": "Ele entra na sala. Todos se calam. Até você. Você está surdo e mudo."
            }
        }

        deck = []
        for suit in suits:
            for value in values:
                deck.append(Card(suit, value, curses[value][suit]))
        
        # Adiciona o Coringa
        deck.append(Card("Joker", "Joker", "A realidade se dobra. Nada é certo. Você é muitos. Ou ninguém."))
        
        return deck

    def _shuffle_deck(self):
        random.shuffle(self.deck)

    def _draw_card(self) -> Card:
        if not self.deck:
            self.deck = self._create_deck()
            self._shuffle_deck()
        return self.deck.pop()

    def start_game(self):
        """Inicia um novo jogo com duas cartas para o jogador"""
        self.player_hand = [self._draw_card(), self._draw_card()]
        self.dealer_hand = [self._draw_card()]

    def hit(self) -> Card:
        """Jogador pede uma carta"""
        card = self._draw_card()
        self.player_hand.append(card)
        return card

    def stand(self) -> int:
        """Jogador para de pedir cartas e o dealer joga"""
        while self.get_dealer_score() < 17:
            self.dealer_hand.append(self._draw_card())
        return self.get_dealer_score()

    def get_score(self) -> int:
        """Calcula a pontuacao do jogador."""
        score = 0
        aces = 0

        for card in self.player_hand:
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

    def get_dealer_score(self) -> int:
        """Calcula a pontuacao do dealer."""
        score = 0
        aces = 0

        for card in self.dealer_hand:
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


    def is_bust(self) -> bool:
        """Verifica se o jogador estourou"""
        return self.get_score() > 21

    def get_hand_str(self) -> str:
        """Retorna a mão do jogador como string"""
        return ", ".join(str(card) for card in self.player_hand)

    def get_curse(self) -> str:
        """Retorna a maldição da última carta que fez o jogador estourar"""
        if self.player_hand:
            return self.player_hand[-1].curse
        return ""

    def get_result(self) -> str:
        """Retorna o resultado do jogo"""
        player_score = self.get_score()
        dealer_score = self.get_dealer_score()

        if player_score > 21:
            return "💀 Você estourou! A maldição das cartas te atingiu..."
        elif dealer_score > 21:
            return "🎉 O dealer estourou! Você venceu!"
        elif player_score > dealer_score:
            return "🎉 Você venceu!"
        elif player_score < dealer_score:
            return "😈 O dealer venceu!"
        else:
            return "🤝 Empate!"
