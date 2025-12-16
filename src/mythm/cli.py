from mythm.tools import bpm, chart, make_chart
import typer
from mythm import runtime
from pathlib import Path
from typing import Annotated

app = typer.Typer()


@app.command()
def play():
    runtime.main()

@app.command('chart')
def gen_chart(song_dir: Annotated[Path, typer.Option()] = Path('songs'), artist: Annotated[str | None, typer.Option()] = None):
    make_chart.main(song_dir)

@app.command()
def update_bpm(song_dir: Annotated[Path, typer.Option()] = Path('songs'), artist: Annotated[str | None, typer.Option()] = None):
    bpm.main(song_dir)
    
if __name__ == "__main__":
    app()