class ChessValidator:
    def __init__(self):
        self.board = {}
        self.reset_board()
        self.turn = 'white'
        self.move_count = 0

    def reset_board(self):
        self.board = {}
        backline = ['R', 'N', 'B', 'Q', 'K', 'B', 'N', 'R']
        for col_idx, col in enumerate(['a', 'b', 'c', 'd', 'e', 'f', 'g', 'h']):
            self.board[f"{col}1"] = ('white', backline[col_idx])
            self.board[f"{col}2"] = ('white', 'P')
            self.board[f"{col}7"] = ('black', 'P')
            self.board[f"{col}8"] = ('black', backline[col_idx])

    @staticmethod
    def parse_pos(pos):
        col = ord(pos[0]) - ord('a')
        row = int(pos[1]) - 1
        return col, row

    @staticmethod
    def to_pos(col, row):
        return f"{chr(col + ord('a'))}{row + 1}"

    def is_path_clear(self, start, end):
        c1, r1 = self.parse_pos(start)
        c2, r2 = self.parse_pos(end)
        dc = (c2 - c1) // max(1, abs(c2 - c1)) if c2 != c1 else 0
        dr = (r2 - r1) // max(1, abs(r2 - r1)) if r2 != r1 else 0

        curr_c = c1 + dc
        curr_r = r1 + dr
        while (curr_c, curr_r) != (c2, r2):
            if self.to_pos(curr_c, curr_r) in self.board:
                return False
            curr_c += dc
            curr_r += dr
        return True

    def validate_and_play(self, moves_text):
        lines = [line.strip() for line in moves_text.strip().split('\n') if line.strip()]
        if not lines:
            return False, "Die Zugdatei ist leer.", 0, None

        self.reset_board()
        self.turn = 'white'
        self.move_count = 0

        for line_num, line in enumerate(lines, 1):
            parts = line.split()
            if len(parts) != 2:
                return False, f"Zeile {line_num}: Ungueltiges Format '{line}'.", self.move_count, None

            start, end = parts[0].lower(), parts[1].lower()

            if start not in self.board:
                return False, f"Zeile {line_num}: Kein Spielstein auf {start}.", self.move_count, None

            color, piece = self.board[start]
            if color != self.turn:
                return False, f"Zeile {line_num}: {color.capitalize()} ist nicht am Zug.", self.move_count, None

            if end in self.board and self.board[end][0] == color:
                return False, f"Zeile {line_num}: Zielfeld {end} ist von eigener Figur besetzt.", self.move_count, None

            valid = self.is_legal_move(piece, color, start, end)
            if not valid:
                return False, f"Zeile {line_num}: Ungueltiger Zug fuer {piece} ({start} nach {end}).", self.move_count, None

            self.board[end] = self.board.pop(start)
            self.move_count += 1
            self.turn = 'black' if self.turn == 'white' else 'white'

        winner = "Schwarz" if self.turn == 'white' else "Weiss"
        return True, "Partie erfolgreich validiert.", self.move_count, winner

    def is_legal_move(self, piece, color, start, end):
        c1, r1 = self.parse_pos(start)
        c2, r2 = self.parse_pos(end)
        dc = c2 - c1
        dr = r2 - r1

        if piece == 'P':
            direction = 1 if color == 'white' else -1
            start_row = 1 if color == 'white' else 6
            if dc == 0 and dr == direction and end not in self.board:
                return True
            if dc == 0 and dr == 2 * direction and r1 == start_row and end not in self.board:
                in_between = self.to_pos(c1, r1 + direction)
                return in_between not in self.board
            if abs(dc) == 1 and dr == direction and end in self.board and self.board[end][0] != color:
                return True
            return False

        elif piece == 'N':
            return (abs(dc), abs(dr)) in [(1, 2), (2, 1)]

        elif piece == 'B':
            return abs(dc) == abs(dr) and self.is_path_clear(start, end)

        elif piece == 'R':
            return (dc == 0 or dr == 0) and self.is_path_clear(start, end)

        elif piece == 'Q':
            return (dc == 0 or dr == 0 or abs(dc) == abs(dr)) and self.is_path_clear(start, end)

        elif piece == 'K':
            return max(abs(dc), abs(dr)) == 1

        return False

    def generate_board_svg(self):
        piece_symbols = {
            ('white', 'K'): '&#9812;', ('white', 'Q'): '&#9813;',
            ('white', 'R'): '&#9814;', ('white', 'B'): '&#9815;',
            ('white', 'N'): '&#9816;', ('white', 'P'): '&#9817;',
            ('black', 'K'): '&#9818;', ('black', 'Q'): '&#9819;',
            ('black', 'R'): '&#9820;', ('black', 'B'): '&#9821;',
            ('black', 'N'): '&#9822;', ('black', 'P'): '&#9823;',
        }
        tile_size = 50
        board_size = tile_size * 8
        elements = [f'<svg xmlns="http://www.w3.org/2000/svg" width="{board_size}" height="{board_size}" viewBox="0 0 {board_size} {board_size}">']

        for row in range(8):
            for col in range(8):
                x = col * tile_size
                y = (7 - row) * tile_size
                is_light = (row + col) % 2 != 0
                color = '#f0d9b5' if is_light else '#b58863'
                elements.append(f'<rect x="{x}" y="{y}" width="{tile_size}" height="{tile_size}" fill="{color}"/>')

                pos_key = f"{chr(col + ord('a'))}{row + 1}"
                if pos_key in self.board:
                    p_color, p_type = self.board[pos_key]
                    sym = piece_symbols.get((p_color, p_type), '')
                    font_color = '#ffffff' if p_color == 'white' else '#000000'
                    stroke = '#000000' if p_color == 'white' else '#333333'
                    elements.append(
                        f'<text x="{x + 25}" y="{y + 38}" font-size="36" text-anchor="middle" '
                        f'fill="{font_color}" stroke="{stroke}" stroke-width="1">{sym}</text>'
                    )

        elements.append('</svg>')
        return "".join(elements)