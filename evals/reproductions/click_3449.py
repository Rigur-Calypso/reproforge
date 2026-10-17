from click import command, echo_via_pager
from click.testing import CliRunner


def test_echo_via_pager_does_not_close_borrowed_stdout():
    @command()
    def cli():
        echo_via_pager("Hello, Click!")

    result = CliRunner().invoke(cli)
    assert result.exit_code == 0
