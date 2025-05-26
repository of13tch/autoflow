from time import sleep

from rich.console import Console

console = Console()
tasks = [f"task {n}" for n in range(1, 5)]
title = "Processing tasks"
with console.status(f"[bold green]{title}") as status:
    while tasks:
        task = tasks.pop(0)
        sleep(1)
        console.log(f"{task} complete")
        status.update(f"[bold green]{title} - {task} complete")
