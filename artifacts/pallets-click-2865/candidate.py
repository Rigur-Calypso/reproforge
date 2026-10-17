import faulthandler

import click
from click.testing import CliRunner


def test_clirunner_faulthandler():
    @click.command()
    def cli():
        faulthandler.enable()
        click.echo("ok")

    runner = CliRunner()
    try:
        result = runner.invoke(cli, catch_exceptions=False)
        assert result.exit_code == 0
        assert result.output == "ok\n"
    finally:
        faulthandler.disable()