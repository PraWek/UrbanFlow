# Этап 1: независимые модели SimPy

В каталоге находятся семь полностью независимых учебных моделей из
[`stage-1-simpy.md`](../openspec/stages/stage-1-simpy.md). 

Во всех моделях время измеряется в секундах, расстояние — в метрах, скорость —
в метрах в секунду. Интервалы зелёного включают начало и не включают конец;
завершение движения ровно на границе разрешено.

Каждый пакет содержит собственные сущности, процессы, журнал и точку запуска.


| Задание | Пакет | Содержание |
| --- | --- | --- |
| 1 | `01_traffic_light` | Цикл зелёный → жёлтый → красный |
| 2 | `02_parallel_travel` | Одновременное движение автомобиля и пешехода |
| 3 | `03_random_flows` | Независимые случайные потоки участников |
| 4 | `04_signalized_crossing` | FIFO-очереди у регулируемого перехода |
| 5 | `05_finite_approach` | Ограниченная вместимость участка A |
| 6 | `06_downstream_spillback` | Блокирование перехода заполненным участком B |
| 7 | `07_coordinated_corridor` | Три направления и согласованные светофоры |

## Установка и запуск

Из каталога `stage1-dao`:

```powershell
& ../.venv/Scripts/python.exe -m pip install -r requirements.txt
& ../.venv/Scripts/python.exe ./01_traffic_light/simulation.py
& ../.venv/Scripts/python.exe ./02_parallel_travel/simulation.py
& ../.venv/Scripts/python.exe ./03_random_flows/simulation.py
& ../.venv/Scripts/python.exe ./04_signalized_crossing/simulation.py
& ../.venv/Scripts/python.exe ./05_finite_approach/simulation.py
& ../.venv/Scripts/python.exe ./06_downstream_spillback/simulation.py
& ../.venv/Scripts/python.exe ./07_coordinated_corridor/simulation.py
```

Все проверки запускаются одной командой:

```powershell
& ../.venv/Scripts/python.exe -m unittest discover -s . -p "test_*.py" -v
```

У каждого упражнения есть собственный каталог `tests`. Например, только тесты
модели регулируемого перехода запускаются так:

```powershell
& ../.venv/Scripts/python.exe -m unittest discover -s 04_signalized_crossing/tests -t . -v
```
