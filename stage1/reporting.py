"""Консольный отчёт и экспорт журналов, участников и мониторинга"""

import csv
import json
from pathlib import Path


def display(result, show_log=False):
    print(f"Exercise {result.exercise} / {result.scenario}: t={result.finished_at:g} s")
    if show_log:
        for row in result.events:
            details = " ".join(f"{k}={v}" for k, v in row.items()
                               if k not in ("time", "actor", "event"))
            print(f"  {row['time']:9.3f}  {row['actor']:20}  {row['event']:22} {details}")
    for kind in ("car", "pedestrian"):
        metrics = result.summary()[kind]
        if metrics["created"]:
            print(f"  {kind}: {metrics['completed']}/{metrics['created']} completed; "
                  f"mean queue wait={metrics['mean_queue_wait']:.3f} s")


def write_csv(path, rows):
    fields = list(dict.fromkeys(key for row in rows for key in row))
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        if fields:
            writer.writeheader()
            writer.writerows(rows)


def export(result, output):
    folder = Path(output) / f"exercise{result.exercise:02d}_{result.scenario}"
    folder.mkdir(parents=True, exist_ok=True)
    write_csv(folder / "participants.csv", [p.to_dict() for p in result.records])
    write_csv(folder / "events.csv", result.events)
    write_csv(folder / "monitoring.csv", result.monitoring)
    (folder / "summary.json").write_text(
        json.dumps(result.summary(), ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    return folder
