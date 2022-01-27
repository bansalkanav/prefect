"""
Command line interface for working with Orion
"""
import json
import shutil
import subprocess
import os

import anyio
from functools import partial
from string import Template
import typer

import prefect
from prefect.cli.base import app, console
from prefect.cli.orion import start as start_orion
from prefect.utilities.asyncio import sync_compatible
from prefect.utilities.filesystem import tmpchdir
from prefect.cli.orion import open_process_and_stream_output
from prefect.flow_runners import get_prefect_image_name

DEV_HELP = """
Commands for development.

Note that many of these commands require extra dependencies (such as npm and MkDocs) to function properly.
"""
dev_app = typer.Typer(name="dev", short_help="Commands for development.", help=DEV_HELP)
app.add_typer(dev_app)


@dev_app.command()
def build_docs(
    schema_path: str = None,
):
    """
    Builds REST API reference documentation for static display.

    Note that this command only functions properly with an editable install.
    """
    # Delay this import so we don't instantiate the API uncessarily
    from prefect.orion.api.server import app as orion_fastapi_app

    schema = orion_fastapi_app.openapi()

    if not schema_path:
        schema_path = (
            prefect.__root_path__ / "docs" / "api-ref" / "schema.json"
        ).absolute()
    # overwrite info for display purposes
    schema["info"] = {}
    with open(schema_path, "w") as f:
        json.dump(schema, f)
    console.print(f"OpenAPI schema written to {schema_path}")


BUILD_UI_HELP = f"""
Installs dependencies and builds UI locally.

The built UI will be located at {prefect.__root_path__ / "orion-ui"}

Requires npm.
"""


@dev_app.command(help=BUILD_UI_HELP)
def build_ui():
    with tmpchdir(prefect.__root_path__):
        with tmpchdir(prefect.__root_path__ / "orion-ui"):

            console.print("Installing npm packages...")
            subprocess.check_output(["npm", "ci", "install"])

            console.print("Building for distribution...")
            env = os.environ.copy()
            env["ORION_UI_SERVE_BASE"] = "/"
            subprocess.check_output(["npm", "run", "build"], env=env)

        if os.path.exists(prefect.__ui_static_path__):
            console.print("Removing existing build files...")
            shutil.rmtree(prefect.__ui_static_path__)

        console.print("Copying build into src...")
        shutil.copytree("orion-ui/dist", prefect.__ui_static_path__)

    console.print("Complete!")


@dev_app.command()
@sync_compatible
async def ui():
    """
    Starts a hot-reloading dev UI.
    """
    with tmpchdir(prefect.__root_path__):
        with tmpchdir(prefect.__root_path__ / "orion-ui"):
            console.print("Installing npm packages...")
            subprocess.check_output(["npm", "install"])

            console.print("Starting UI development server...")
            await open_process_and_stream_output(command=["npm", "run", "serve"])


@dev_app.command()
@sync_compatible
async def start(agent: bool = True):
    """
    Starts a hot-reloading dev server and UI.

    Args:
        agent: Whether or not the Orion Server should spin up an agent
    """
    async with anyio.create_task_group() as tg:
        tg.start_soon(partial(start_orion, ui=False, agent=agent))
        tg.start_soon(ui)


@dev_app.command()
def kubernetes_manifest():
    """
    Generates a kubernetes manifest for development.

    Example:
        $ prefect dev kubernetes-manifest | kubectl apply -f -
    """

    template = Template(
        (
            prefect.__module_path__ / "cli" / "templates" / "kubernetes-dev.yaml"
        ).read_text()
    )
    manifest = template.substitute(
        {
            "prefect_root_directory": prefect.__root_path__,
            "image_name": get_prefect_image_name(),
        }
    )
    print(manifest)
