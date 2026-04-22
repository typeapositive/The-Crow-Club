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
                "Copas": "O seu sangue pulsa fora do ritmo. Seu coração pesa como chumbo. Você sente muita tristeza e seu passado assombra seus pensamentos.",
                "Espadas": "Uma lâmina invisível encosta na sua nuca. A dor é silenciosa, mas real. Não faça movimentos bruscos, ou ela cortará sua pele.",
                "Ouros": "Os dedos ardem ao tocar o ouro. Tudo que reluz te rejeita e queima a sua pele.",
                "Paus": "Sussurros ecoam ao seu redor. Eles sabem o que você fez. E o que você quer fazer. Você entra em estado de paranoia."
            },
            "2": {
                "Copas": "Sua língua enrola. As palavras somem da sua mente. Agora você não consegue mais falar.",
                "Espadas": "Um corte fino se abre no seu braço. Você não viu de onde veio. Esse corte não se fechará até a maldição acabar.",
                "Ouros": "As moedas vibram em seu bolso e depois desaparecem. Você perde todo o dinheiro que estava carregando. E todo dinheiro que entrar no seu bolso desaparecerá até a maldição terminar.",
                "Paus": "Seu pulso treme. Você se sente obrigado a lançar um feitiço (ou dar um soco muito forte) em algum de seus adversários."
            },
            "3": {
                "Copas": "Um calor febril sobe pelas veias. O mundo parece distante. Você sente um grande vazio existencial.",
                "Espadas": "Você ouve passos atrás de si. Ninguém está lá. Os passos não param e parecem mais altos que qualquer outra coisa, perseguindo você.",
                "Ouros": "Seu ouro não deseja mais ser seu. Seu dinheiro inteiro vai para um de seus adversários.",
                "Paus": "Sua mão se move sem comando. Algo assumiu o controle. Você perde o movimento da mão dominante e ela quer estapear qualquer um que se aproxima de você."
            },
            "4": {
                "Copas": "O ar ao seu redor congela. Os outros não parecem notar. Você está com muito, muito frio.",
                "Espadas": "Sente-se observado. Os olhos... eles não piscam. Você vê dois olhos em todo canto escuro que olhar. Eles são assustadores.",
                "Ouros": "Toque de Midas ao contrário. Todo ouro que você tocar, vai se transformar em pó.",
                "Paus": "Sua voz ecoa com fora do seu controle. Você não consegue falar, mas pode gritar."
            },
            "5": {
                "Copas": "Uma memória esquecida ressurge. Você queria mantê-la enterrada. Ela está vívida demais e você tem alucinações visuais e auditivas sobre ela.",
                "Espadas": "O cheiro de ferro preenche o ar. Suas mãos estão cobertas de sangue. Tudo que você tocar, vai sangrar. Mas só você pode ver.",
                "Ouros": "O ouro pesa mais do que devia. Você carrega culpa com ele. Seus bolsos se enchem de ouro, mas cada vez que gastar, revive a sua pior memória.",
                "Paus": "Risos abafados se espalham pelas sombras. Estão rindo de você? Você sente uma paranoia profunda."
            },
            "6": {
                "Copas": "Bloody Mary. Superfícies espelhadas refletem uma mulher assustadora que se aproxima de você cada vez mais. Quando você desvia o olhar, ela volta do início. Quer descobrir o que acontece se não parar de olhar? ",
                "Espadas": "Algo arranha sua perna. Nada visível, mas sangra. A cada uma hora, essa mesma coisa arranha uma parte do seu corpo.",
                "Ouros": "Os números se embaralham diante dos seus olhos e na sua mente. Você desaprende a contar, não consegue ver as horas e não sabe mais quanto dinheiro tem.",
                "Paus": "Você precisa vencer em tudo. Se você falhar, receberá uma chicotada nas costas. O açoite é invisível, mas a dor é real."
            },
            "7": {
                "Copas": "O coração bate forte, descompassado. O medo chegou antes do motivo. Você se assusta com as pequenas coisas.",
                "Espadas": "Senescal da justiça. Você é severamente punido pela lâmina da justiça se mentir. Fale apenas a verdade. Qualquer desonestidade é punida, então também funciona com feéricos que tentarem enganar ou contornar a verdade.",
                "Ouros": "As moedas sussurram entre si. Qualquer dinheiro que você tiver consigo, sussurrará suas maiores inseguranças.",
                "Paus": "As sombras se alongam ao seu redor. Estão te envolvendo. Você fica cego e deverá confiar no seu dealer para guiar seu jogo."
            },
            "8": {
                "Copas": "Uma paixão proibida invade sua mente. Você se apaixona por um adversário.",
                "Espadas": "Uma lâmina paira acima da cabeça. Esperando cair. Ela pode cair a qualquer momento, então é melhor não tirar os olhos dela. Sempre que você olhar para outro lugar, deverá rodar um D20 com a DT 5 para a lâmina não cair. Isso inclui quando você precisar olhar suas cartas. Piscar é permitido.",
                "Ouros": "Riqueza envenenada. Qualquer moeda que você olhar, brilhará como o sol.",
                "Paus": "O tempo desacelera. Cada batida parece um século. Você só consegue falar em câmera lenta."
            },
            "9": {
                "Copas": "Um nome perdido sussurra em seus ouvidos. Alguém do seu passado volta para te assombrar, só você pode ver.",
                "Espadas": "Seu braço pesa como pedra. Só poderá usar uma mão a partir de agora, pois a outra está paralisada.",
                "Ouros": "O som de tilintar se torna insuportável. Qualquer barulho de moedas, taças ou qualquer coisa metálica te causa náusea.",
                "Paus": "O chão vibra sob seus pés. Algo se aproxima por baixo. É difícil manter o equilíbrio e você precisa se segurar em alguma coisa para se manter de pé."
            },
            "10": {
                "Copas": "O seu amor te traiu. Você desconfia de todos os seus amigos e/ou paixões e acha que eles estão conspirando contra você.",
                "Espadas": "Seu sangue gela. Não por medo, maspor premonição. Isso lhe causa uma enorme ansiedade. Você pode (em off) inventar a falsa profecia a qual tem certeza de que é real e está próxima de se realizar.",
                "Ouros": "O ouro da necromante. Você vê gente morta sempre que tocar em dinheiro.",
                "Paus": "Seus membros se movem por vontade própria. A dança da perdição. Você precisa dançar a cada 10 minutos enquanto estiver acordado."
            },
            "J": {
                "Copas": "Um rosto familiar aparece nos olhos de todos. Mas está morto. Seus adversários estão com uma aparência horrível de cadáver em decomposição. E cheiro também...",
                "Espadas": "Retaliação. Você precisa punir um de seus adversários sempre que ele te irritar. A punição fica a seu critério.",
                "Ouros": "As moedas pulam da sua bolsa. Elas escolheram outro dono. Pode estar com qualquer pessoa ao seu redor. Literalmente qualquer pessoa.",
                "Paus": "O morto-vivo. Seu toque é gelado como o de um vampiro. E você sente sede de sangue. A sede não é incontrolável, mas você realmente quer tomar um pouquinho e não vai descansar até conseguir."
            },
            "Q": {
                "Copas": "Você sente um amor profundo por algum de seus adversários, mas sabe que não é correspondido. Se você tocar essa pessoa, sua mão arde como fogo. Se olhar para ela, sente que está se afogando.",
                "Espadas": "Um feitiço se prende à sua língua. Você não fala, você sussurra.",
                "Ouros": "Eles sorriem para você, com olhos feitos de rubis. Você paralisa por cinco minutos sempre que olhar nos olhos de alguém, mas é muito tentador. Os rubis te atraem bastante. Sempre que olhar para alguém, rode um D20, DT 10 para lutar contra a vontade de olhar nos olhos.",
                "Paus": "Sua pele formiga. As runas antigas despertam sob sua carne. Seu corpo inteiro está coçando."
            },
            "K": {
                "Copas": "Uma voz autoritária ordena: ceda. Você obedece, sem saber a quem. A próxima coisa que lhe pedirem, você é obrigado a aceitar.",
                "Espadas": "Seu peito dói por vergonha profunda. Você agora fala gaguejando.",
                "Ouros": "O Rei exige tributo. Algo seu agora pertence a ele. Dê tudo o que você tem ao dealer. E se não tiver nada, dê o seu sangue.",
                "Paus": "Não sei o que dizer. Você está surdo e mudo. É isso."
            }
        }

        deck = []
        for suit in suits:
            for value in values:
                deck.append(Card(suit, value, curses[value][suit]))
        
        # Adiciona o Coringa
        deck.append(Card("Joker", "Joker", "Tudo e nada ao mesmo tempo. O Coringa é imprevisível e pode tanto te ajudar quanto te prejudicar. Ele pode assumir o valor de qualquer carta."))
        
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
