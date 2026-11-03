"""Human-readable diagnostics on stderr; stdout remains machine-readable."""

from __future__ import annotations

from contextlib import contextmanager
from typing import Iterator

from rich.console import Console
from rich.progress import (
    BarColumn,
    DownloadColumn,
    Progress,
    SpinnerColumn,
    TaskProgressColumn,
    TextColumn,
    TimeRemainingColumn,
    TransferSpeedColumn,
)


def phase(message: str) -> None:
    # Messages are fixed labels, never raw URLs, headers or credentials.
    Console(stderr=True, markup=False, highlight=False).print(f"[阶段] {message}")


@contextmanager
def stage(message: str) -> Iterator[None]:
    phase(message)
    try:
        yield
    except BaseException:
        phase(f"{message}：未完成")
        raise
    else:
        phase(f"{message}：完成")


class ByteProgress:
    def __init__(self, total: int | None, completed: int):
        self.console = Console(stderr=True, markup=False, highlight=False)
        self.completed = completed
        self.total = total
        self.progress = Progress(
            SpinnerColumn(),
            TextColumn("下载"),
            BarColumn(),
            TaskProgressColumn(),
            DownloadColumn(),
            TransferSpeedColumn(),
            TimeRemainingColumn(),
            console=self.console,
            disable=not self.console.is_terminal,
            refresh_per_second=5,
        )
        self.task = self.progress.add_task("下载", total=total, completed=completed)

    def advance(self, amount: int) -> None:
        self.completed += amount
        self.progress.update(self.task, advance=amount)

    def __enter__(self) -> ByteProgress:
        total = str(self.total) if self.total is not None else "未知"
        phase(f"{'断点续传' if self.completed else '开始下载'}：{self.completed}/{total} 字节")
        self.progress.start()
        return self

    def __exit__(self, exc_type: object, exc: object, traceback: object) -> None:
        self.progress.stop()
        total = str(self.total) if self.total is not None else "未知"
        phase(f"{'下载传输完成' if exc_type is None else '下载传输中断'}：{self.completed}/{total} 字节")
