"""
Spider Node entrypoint.

Run with: python3 -m leviathan.spider
"""
import uvicorn


def main():
    """Run Spider Node API server."""
    uvicorn.run(
        "leviathan.spider.api:app",
        host="0.0.0.0",
        port=8001,
        log_level="info"
    )


if __name__ == "__main__":
    main()
