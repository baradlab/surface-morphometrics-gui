"""Click entry point for the `morphometrics gui` plugin command.

Intentionally import-light: must NOT import napari/Qt at module load time, so that
`morphometrics --help` (which loads this to read the command's help) stays fast.
"""
import click


@click.command(name="gui")
def gui():
    """Launch the napari surface-morphometrics GUI."""
    from .main import main   # heavy import deferred to invocation time
    main()
