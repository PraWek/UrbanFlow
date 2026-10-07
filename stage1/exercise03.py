"""Упражнение 3: независимые пуассоновские потоки на протяжении 600 с"""

from .flows import run_movement


def run(seed=42):
    return run_movement(3, seed)


if __name__ == "__main__":
    from .reporting import display
    display(run(), show_log=True)
