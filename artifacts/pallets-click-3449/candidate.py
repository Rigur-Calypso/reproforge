import click
from click.testing import CliRunner


def test_echo_via_pager():
    @click.command()
    def cli():
        click.echo_via_pager("Hello, Click!")

    runner = CliRunner()
    result = runner.invoke(cli)
    assert result.exit_code == 0
    assert "Hello, Click!" in result.output