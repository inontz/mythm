import typer
from mythm import runtime, chart, bpm
from pathlib import Path
from typing import Annotated

app = typer.Typer()


@app.command()
def play():
    runtime.main()

@app.command('chart')
def gen_chart(song_dir: Annotated[Path, typer.Option()] = Path('songs'), artist: Annotated[str | None, typer.Option()] = None):
    if artist is not None:
        song_dir = song_dir.joinpath(artist)
    chart.main(song_dir)

@app.command()
def update_bpm(song_dir: Annotated[Path, typer.Option()] = Path('songs'), artist: Annotated[str | None, typer.Option()] = None):
    if artist is not None:
        song_dir = song_dir.joinpath(artist)
    bpm.main(song_dir)