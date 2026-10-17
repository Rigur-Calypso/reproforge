import faulthandler
import click
from click.testing import CliRunner


def test_clirunner_supports_faulthandler():
    @click.command()
    def cli():
        faulthandler.enable()

    runner = CliRunner()
    result = runner.invoke(cli, catch_exceptions=False)
    assert result.exit_code == 0
