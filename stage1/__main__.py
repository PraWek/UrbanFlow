"""python -m stage1 --exercise all --output stage1/results"""

import argparse

from . import exercise01, exercise02, exercise03, exercise04, exercise05, exercise06, exercise07
from .reporting import display, export


def main():
    parser = argparse.ArgumentParser(description="UrbanFlow: семь упражнений SimPy")
    parser.add_argument("--exercise", choices=["all", *map(str, range(1, 8))], default="all")
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--log", action="store_true", help="Вывести полный журнал событий")
    parser.add_argument("--output", help="Папка для CSV и JSON")
    args = parser.parse_args()
    exercises = range(1, 8) if args.exercise == "all" else [int(args.exercise)]
    for number in exercises:
        if number == 1:
            results = [exercise01.run()]
        elif number == 2:
            results = [exercise02.run()]
        elif number == 3:
            results = [exercise03.run(args.seed)]
        elif number == 4:
            results = [exercise04.demo(), exercise04.run(args.seed)]
        elif number == 5:
            results = [exercise05.demo(), exercise05.run(args.seed)]
        elif number == 6:
            results = [exercise06.demo(0), exercise06.demo(), *exercise06.compare(args.seed)]
        else:
            results = [exercise07.demo(), exercise07.demo(True), exercise07.run(args.seed)]
        for result in results:
            display(result, args.log or number == 1)
            if args.output:
                print(f"  Saved: {export(result, args.output)}")


if __name__ == "__main__":
    main()
