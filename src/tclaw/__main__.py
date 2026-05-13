"""python -m tclaw 入口。"""

from .main import main

if __name__ == "__main__":
    import asyncio
    asyncio.run(main())
