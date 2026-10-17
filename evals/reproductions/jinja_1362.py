import asyncio
from jinja2.nativetypes import NativeEnvironment


def test_native_environment_render_async_list():
    env = NativeEnvironment(enable_async=True)
    template = env.from_string("{{ items }}")

    async def render():
        return await template.render_async(items=[1, 2, 3, 4, 5, 6, 7, 8, 9])

    result = asyncio.run(render())
    assert result == [1, 2, 3, 4, 5, 6, 7, 8, 9]
