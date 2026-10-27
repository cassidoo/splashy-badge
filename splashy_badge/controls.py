from physics import MONA


class Controls:
    def __init__(self, up, down, left, right, select, back, labels=None):
        # Shared with setup; an empty label makes its button drop only Monas.
        self.labels = labels if labels is not None else ["word"] * 3
        self.up, self.down = up, down
        self.left, self.right = left, right
        self.select, self.back = select, back

    def apply(self, badge, pool, dt):
        buttons, pad = badge.buttons, badge.pad
        up = buttons.pressed(self.up) or buttons.held(self.up)
        down = buttons.pressed(self.down) or buttons.held(self.down)
        pool.water(int(up) - int(down), dt)
        full = False
        for kind, action in enumerate((self.left, self.right, self.select)):
            if buttons.pressed(action):
                # Each word appears once; further drops are Monas.
                if not self.labels[kind] or any(obj[6] == kind for obj in pool.objects):
                    kind = MONA
                full = not pool.add(kind) or full
        if pad.pressed(self.select):
            pool.clear()
        if pad.pressed(self.back):
            pool.cycle_color()
        move = pad.direction()
        return move.x, move.y, full
