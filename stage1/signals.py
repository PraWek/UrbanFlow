"""Контроллеры уведомляют процессы через Event; опроса по шагам нет"""


class Signal:
    def __init__(self, env, phases, result, name):
        self.env = env
        self.phases = phases  # имя разрешённого движения, длительность
        self.period = sum(duration for _, duration in phases)
        self.result = result
        self.name = name
        self.changed = env.event()
        self.current = phases[0][0]
        env.process(self.run())

    def window(self):
        """Расписание по env.now исключает зависимость от порядка callbacks"""
        position = self.env.now % self.period
        cycle_start = self.env.now - position
        end = 0
        for name, duration in self.phases:
            end += duration
            if position < end:
                return name, cycle_start + end
        raise RuntimeError("Не найден интервал светофора")

    def permits(self, movement, duration):
        name, end = self.window()
        return name == movement and self.env.now + duration <= end

    def run(self):
        while True:
            for name, duration in self.phases:
                self.current = name
                self.result.log(self.env.now, self.name, "signal", allowed=name)
                previous, self.changed = self.changed, self.env.event()
                previous.succeed(name)
                yield self.env.timeout(duration)


def receiver_phases(start, end):
    """Один зелёный интервал в общем 60-секундном цикле"""
    phases = []
    if start:
        phases.append(("red", start))
    phases.append(("green", end - start))
    if end < 60:
        phases.append(("red", 60 - end))
    return phases
