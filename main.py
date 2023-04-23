import logging
import click
from dotenv import load_dotenv

load_dotenv()
from scraper.main import Scraper

logging.basicConfig(level=logging.INFO)


@click.command()
@click.option(
    "--headless",
    default=True,
    help="Run in headless mode",
    type=click.BOOL,
)
@click.option(
    "--query",
    default="frete grátis para todo brasil",
    help="Ads query",
    type=click.STRING,
)
@click.option(
    "--rounds",
    default=1,
    help="Rounds of scroll height to be captured",
    type=click.INT,
)
def main(headless, query, rounds):
    with Scraper(headless=headless) as scraper:
        params = {"q": query, "ad_type": "all"}
        scraper.scrape(params=params, rounds=rounds)


if __name__ == "__main__":
    main()
