from physics import LABELS

STATE_KEY = "splashy_badge"
MAX_LENGTH = 16
FIELDS = ("Handle", "Title", "Pronouns")
BUTTONS = ("left", "middle", "right")
PRESETS = (
    ("@mona", "@octocat"),
    ("universe", "devex", "engineer", "developer", "designer", "dev advocate", "product",
     "manager", "student", "founder", "speaker", "hubber"),
    ("she/her", "he/him", "they/them", "she/they", "he/they", "any/all", ""),
)
COLORS = ((255, 173, 218), (255, 220, 137), (180, 191, 255))

LETTER_ROWS = ("1234567890", "qwertyuiop", "asdfghjkl", "zxcvbnm-/@")
SYMBOL_ROWS = ("!@#$%^&*()", "-_=+[]{}\\|", ";:'\",./?~", "<>`")
# Bottom row: (label, action, width in key units).
ACTIONS = (("aA", "shift", 1.5), ("#+=", "symbols", 1.5), ("space", " ", 4),
           ("del", "delete", 1.5), ("done", "done", 1.5))

WIDTH = 320
MARGIN = 4
GAP = 3
FIELD_TOP = 24
FIELD_HEIGHT = 30
KEY_TOP = FIELD_TOP + FIELD_HEIGHT + 6
KEY_HEIGHT = 25
UNIT = (WIDTH - MARGIN * 2 - GAP * 9) // 10
ROW_TOP = 30
ROW_HEIGHT = 38


def clean(value):
    """Keep printable ASCII the font can draw, trimmed to a badge-sized label."""
    if not isinstance(value, str):
        return None
    return "".join(c for c in value if 32 <= ord(c) < 127).strip()[:MAX_LENGTH]


def _state(state):
    if state is None:
        from badgeware import State as state
    return state


def handle(username):
    username = clean(username or "")
    return clean("@" + username.lstrip("@")) if username.lstrip("@") else None


def defaults(username=None):
    return [handle(username) or LABELS[0]] + list(LABELS[1:])


def load(state=None, username=None):
    """Return (labels, saved); saved is False until labels have been stored."""
    fallback = defaults(username)
    data = {}
    try:
        _state(state).load(STATE_KEY, data)
    except (ImportError, OSError, ValueError, TypeError):
        pass
    saved = data.get("labels")
    if not isinstance(saved, list) or len(saved) != len(LABELS):
        return fallback, False
    labels = [clean(value) for value in saved]
    return [default if value is None else value
            for value, default in zip(labels, fallback)], True


def save(labels, state=None):
    try:
        _state(state).save(STATE_KEY, {"labels": list(labels)})
        return True
    except (ImportError, OSError, ValueError, TypeError):
        return False


def presets(kind, extra=None):
    options = list(PRESETS[kind])
    if kind == 0 and handle(extra) and handle(extra) not in options:
        options.insert(0, handle(extra))
    return options


class Key:
    def __init__(self, label, action, left, top, width):
        self.label, self.action = label, action
        self.left, self.top, self.width = left, top, width
        self.centre = left + width / 2


class Setup:
    """Pick or type the three bottom-button labels on the badge itself."""

    def __init__(self, screen, color, font, labels, buttons, username=None, welcome=False):
        self.screen, self.color = screen, color
        self.welcome = welcome
        self.labels = list(labels)
        self.buttons = buttons
        self.username = username
        self.row = 0
        self.typing = None
        self.value = ""
        self.shift = False
        self.symbols = False
        self.rows = []
        self.key_row = self.key_column = 0
        self.fonts = (getattr(font, "sins", None), getattr(font, "yesterday", None),
                      getattr(font, "nope", None))
        self.white = color.rgb(255, 255, 255)
        self.dim = color.rgb(150, 180, 196)
        self.dark = color.rgb(5, 12, 23)
        self.panel = color.rgb(16, 34, 52)
        self.accents = tuple(color.rgb(*rgb) for rgb in COLORS)
        self.tints = tuple(color.rgb(*(int(v * 0.28) for v in rgb)) for rgb in COLORS)

    # Input -----------------------------------------------------------------

    def update(self, pressed):
        """Handle this frame's presses; returns False once setup is finished."""
        b = self.buttons
        if self.typing is not None:
            return self.update_keys(pressed, b)
        if pressed(b["up"]):
            self.row = (self.row - 1) % (len(FIELDS) + 1)
        if pressed(b["down"]):
            self.row = (self.row + 1) % (len(FIELDS) + 1)
        if self.row < len(FIELDS):
            step = int(bool(pressed(b["right"]))) - int(bool(pressed(b["left"])))
            if step:
                self.cycle(self.row, step)
            if pressed(b["select"]):
                self.start_typing(self.row)
                return True
        elif pressed(b["select"]):
            return False
        return not (pressed(b["back"]) or pressed(b["menu"]))

    def cycle(self, kind, step):
        options = presets(kind, self.username)
        current = self.labels[kind]
        if current not in options:
            options.insert(0, current)
        self.labels[kind] = options[(options.index(current) + step) % len(options)]

    def start_typing(self, kind):
        self.typing = kind
        self.value = self.labels[kind]
        self.shift = self.symbols = False
        self.build()
        self.key_row, self.key_column = 1, 0

    def build(self):
        rows = []
        top = KEY_TOP
        for text in SYMBOL_ROWS if self.symbols else LETTER_ROWS:
            if self.shift and not self.symbols:
                text = text.upper()
            left = (WIDTH - len(text) * UNIT - (len(text) - 1) * GAP) // 2
            rows.append([Key(c, c, left + i * (UNIT + GAP), top, UNIT)
                         for i, c in enumerate(text)])
            top += KEY_HEIGHT + GAP
        span = WIDTH - MARGIN * 2 - GAP * (len(ACTIONS) - 1)
        units = sum(width for _, _, width in ACTIONS)
        left, keys = MARGIN, []
        for n, (label, action, width) in enumerate(ACTIONS):
            size = (WIDTH - MARGIN - left if n == len(ACTIONS) - 1
                    else int(span * width / units))
            keys.append(Key(label, action, left, top, size))
            left += size + GAP
        rows.append(keys)
        self.rows = rows
        self.key_row = min(self.key_row, len(rows) - 1)
        self.key_column = min(self.key_column, len(rows[self.key_row]) - 1)

    def move_row(self, step):
        centre = self.rows[self.key_row][self.key_column].centre
        self.key_row = (self.key_row + step) % len(self.rows)
        keys = self.rows[self.key_row]
        self.key_column = min(range(len(keys)), key=lambda i: abs(keys[i].centre - centre))

    def update_keys(self, pressed, b):
        if pressed(b["right"]):
            self.key_column = (self.key_column + 1) % len(self.rows[self.key_row])
        if pressed(b["left"]):
            self.key_column = (self.key_column - 1) % len(self.rows[self.key_row])
        if pressed(b["down"]):
            self.move_row(1)
        if pressed(b["up"]):
            self.move_row(-1)
        if pressed(b["back"]):
            self.value = self.value[:-1]
        if pressed(b["menu"]):
            return self.finish_typing()
        if pressed(b["select"]):
            self.press(self.rows[self.key_row][self.key_column])
        return True

    def press(self, key):
        if key.action == "shift":
            self.shift = not self.shift
            self.build()
        elif key.action == "symbols":
            self.symbols = not self.symbols
            self.build()
        elif key.action == "delete":
            self.value = self.value[:-1]
        elif key.action == "done":
            self.finish_typing()
        elif len(self.value) < MAX_LENGTH:
            self.value += key.action

    def finish_typing(self):
        self.labels[self.typing] = clean(self.value)
        self.typing = None
        return True

    # Drawing ---------------------------------------------------------------

    def draw_busy(self):
        self.screen.pen = self.dark
        self.screen.clear()
        self.text("Making your words...", WIDTH / 2, 112, self.white, 1, centred=True)

    def text(self, value, x, y, pen, which=1, size=None, centred=False):
        screen = self.screen
        screen.pen = pen
        if self.fonts[which] is not None:
            screen.font = self.fonts[which]
        if centred:
            x -= screen.measure_text(value)[0] / 2
        if size is None:
            screen.text(value, x, y)
        else:
            screen.text(value, x, y, size)

    def draw(self):
        screen = self.screen
        screen.pen = self.dark
        screen.clear()
        if self.typing is None:
            self.draw_list()
        else:
            self.draw_keys()

    def draw_list(self):
        screen = self.screen
        title = "Welcome! Make it yours" if self.welcome else "Splashy Badge setup"
        self.text(title, WIDTH / 2, 6, self.white, 1, centred=True)
        for kind in range(len(FIELDS) + 1):
            top = ROW_TOP + kind * (ROW_HEIGHT + GAP)
            selected = kind == self.row
            if kind == len(FIELDS):
                screen.pen = self.white if selected else self.panel
                screen.rectangle(MARGIN, top, WIDTH - MARGIN * 2, ROW_HEIGHT - 8)
                self.text("Save & return to the pool", WIDTH / 2, top + 7,
                          self.dark if selected else self.white, 1, centred=True)
                continue
            screen.pen = self.accents[kind] if selected else self.tints[kind]
            screen.rectangle(MARGIN, top, WIDTH - MARGIN * 2, ROW_HEIGHT)
            ink = self.dark if selected else self.accents[kind]
            self.text("%s  (%s button)" % (FIELDS[kind], BUTTONS[kind]), MARGIN + 8, top + 3,
                      ink, 2)
            value = self.labels[kind] or "(Monas only)"
            self.text(value, MARGIN + 8, top + 15, self.dark if selected else self.white, 1)
            if selected:
                self.text("<  >", WIDTH - MARGIN - 34, top + 15, self.dark, 1)
        self.text("Up/Down: choose   Left/Right: pick   A: type", WIDTH / 2,
                  226, self.dim, 2, centred=True)

    def draw_keys(self):
        screen = self.screen
        kind = self.typing
        screen.pen = self.tints[kind]
        screen.rectangle(MARGIN, FIELD_TOP, WIDTH - MARGIN * 2, FIELD_HEIGHT)
        self.text("%s (%s button)" % (FIELDS[kind], BUTTONS[kind]), MARGIN + 2, 6,
                  self.accents[kind], 2)
        self.text("%d/%d" % (len(self.value), MAX_LENGTH), WIDTH - MARGIN - 30, 6, self.dim, 2)
        self.text(self.value, MARGIN + 8, FIELD_TOP + 7, self.white, 1)
        cursor = MARGIN + 10 + screen.measure_text(self.value)[0]
        screen.pen = self.accents[kind]
        screen.rectangle(int(cursor), FIELD_TOP + 6, 2, FIELD_HEIGHT - 12)
        for r, keys in enumerate(self.rows):
            for c, key in enumerate(keys):
                selected = r == self.key_row and c == self.key_column
                active = ((key.action == "shift" and self.shift)
                          or (key.action == "symbols" and self.symbols))
                screen.pen = (self.white if selected else
                              self.accents[kind] if active else self.panel)
                screen.rectangle(key.left, key.top, key.width, KEY_HEIGHT)
                ink = self.dark if selected or active else self.white
                self.text(key.label, key.centre, key.top + 5, ink, 1, centred=True)
        self.text("A press   B delete   Menu done", WIDTH / 2, 226, self.dim, 2, centred=True)
