import logging
import os
import pprint
import time
from typing import Any, Dict, List, Union
from seleniumwire import webdriver
from selenium_stealth import stealth
import json
import urllib.parse
from selenium.webdriver.common.desired_capabilities import DesiredCapabilities

from scraper.strategy import Executor


def parse_env_variables(
    env_key: str, default_value: Union[int, str]
) -> Union[int, str]:
    """Attemps to find a env variable and returns a default value if nothing has been found

    Args:
        env_key (str): the env variable key
        default_value (int): the default value

    Returns:
        Union[int, str]: the env variable value
    """
    if isinstance(default_value, int):
        return default_value if not env_key in os.environ else int(os.environ[env_key])
    return default_value if not env_key in os.environ else os.environ[env_key]


CHROME_DRIVER_PATH = parse_env_variables(
    "CHROME_DRIVER_PATH", "/usr/local/bin/chromedriver"
)
CHROME_BROWSER_PATH = parse_env_variables("CHROME_BROWSER_PATH", "/usr/bin/chromium")

URL = "https://www.facebook.com/ads/library/?active_status=all&country=BR&sort_data[direction]=desc&sort_data[mode]=relevancy_monthly_grouped&search_type=keyword_unordered&media_type=all"
# q=frete%20gr%C3%A1tis%20para%20todo%20brasil&
# ad_type=all&
DEFAULT_PARAMS = {"q": "frete grátis para todo brasil", "ad_type": "all"}


def merge_url_query_params(
    url: str, additional_params: Dict[str, str] = DEFAULT_PARAMS
) -> str:
    url_components = urllib.parse.urlparse(url)
    original_params = urllib.parse.parse_qs(url_components.query)
    merged_params = {**original_params, **additional_params}
    updated_query = urllib.parse.urlencode(merged_params, doseq=True)
    return url_components._replace(query=updated_query).geturl()


class Scraper:
    def __init__(self, headless: bool = True, suppress: bool = False) -> None:
        self.suppress = suppress

        self.options: webdriver.ChromeOptions() = webdriver.ChromeOptions()
        if "CHROME_BROWSER_PATH" in os.environ:
            self.options.binary_location = CHROME_BROWSER_PATH
        user_agent = """Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36
        (KHTML, like Gecko) Chrome/60.0.3112.50 Safari/537.36"""
        self.options.add_argument("--start-maximized")
        self.options.add_argument("enable-automation")
        self.options.add_argument("--no-sandbox")
        self.options.add_argument("--disable-dev-shm-usage")
        self.options.add_argument("--disable-browser-side-navigation")
        self.options.add_argument("--disable-gpu")
        self.options.add_argument("--disable-notifications")
        self.options.add_argument("disable-infobars")
        if headless:
            self.options.add_argument("--headless=chrome")
        self.options.add_argument("--force-device-scale-factor=1")
        self.options.add_extension(extension="./I-still-don-t-care-about-cookies.crx")
        # https://stackoverflow.com/questions/56637973/how-to-fix-selenium-devtoolsactiveport-file-doesnt-exist-exception-in-python
        self.options.add_argument("--remote-debugging-port=53717")
        self.options.add_argument(f"user-agent={user_agent}")
        self.options.add_argument("enable-features=NetworkServiceInProcess")
        self.options.add_argument("disable-features=NetworkService")
        self.options.add_argument("--ignore-certificate-errors")
        self.options.add_argument("--log-level=3")

    def __enter__(self):
        # desired_capabilities = DesiredCapabilities.CHROME
        # desired_capabilities["goog:loggingPrefs"] = {"performance": "ALL"}
        seleniumwire_options = {
            "enable_har": True,
            "har_storage_base_dir": "/Users/lorenzotomaz/projects/skunkworks/market_scraper/proxy",
        }
        self.driver = webdriver.Chrome(
            CHROME_DRIVER_PATH,
            options=self.options,
            seleniumwire_options=seleniumwire_options,
        )
        self.driver.set_script_timeout(1000)
        self.driver.set_page_load_timeout(100)
        # Defining a fix window size at starts avoids chromium initializing with mobile screen settings
        # https://bugs.chromium.org/p/chromium/issues/detail?id=904207
        # self.driver.set_window_size(1040, 970)
        self.driver.maximize_window()
        stealth(
            self.driver,
            languages=["en-US", "en"],
            vendor="Google Inc.",
            platform="Win32",
            webgl_vendor="Intel Inc.",
            renderer="Intel Iris OpenGL Engine",
            fix_hairline=True,
        )
        return self

    def get_network_traffic(self):
        return self.driver.get_log("performance")

    def persist_network_traffic(self, file_path: str = "network_log.json"):
        logs = self.get_network_traffic()
        with open(file_path, "w", encoding="utf-8") as f:
            parsed_logs = []
            # Iterates every logs and parses it using JSON
            for log in logs:
                network_log = json.loads(log["message"])["message"]

                # Checks if the current 'method' key has any
                # Network related value.
                if (
                    "Network.response" in network_log["method"]
                    or "Network.request" in network_log["method"]
                    or "Network.webSocket" in network_log["method"]
                ):
                    parsed_logs.append(log)
            f.write(json.dumps(parsed_logs, indent=4))

    def save_network_logs(self, file_path: str = "network_log.json") -> Dict[Any, Any]:
        if os.path.isfile(file_path):
            os.remove(file_path)
        entries = json.loads(self.driver.har)["log"]["entries"]
        Executor().save(entries=entries, file_path=file_path)
        return entries

    def to_excel(self, entries: Dict[Any, Any], file_path: str = "network_log.xlsx"):
        if os.path.isfile(file_path):
            os.remove(file_path)
        Executor().to_excel(entries=entries, file_path=file_path)

    def see_more(self):
        try:
            time.sleep(10)
            elements = self.driver.find_element(
                "xpath", "//span[contains(text(), 'See more')]"
            )
            if isinstance(elements, list):
                element = elements[0]
            else:
                element = elements
            element.click()
            time.sleep(5)
        except Exception as e:
            logging.error(e)

    def load_step(self, i, page_height, retries=3):
        try:
            print(f"Round #{i}")
            self.driver.execute_script(
                "window.scrollTo(0, document.body.scrollHeight);"
            )
            self.see_more()
            time.sleep(5)
            new_page_height = self.driver.execute_script(
                "return document.body.scrollHeight"
            )
            if (new_page_height - page_height) < 1000:
                print("No more ads to load")
                return False
            return True
        except Exception as e:
            logging.error(e)
            if retries > 0:
                print("Retrying...")
                return self.load_step(i, page_height, retries - 1)

    def scrape(
        self,
        params: Dict[str, str] = DEFAULT_PARAMS,
        rounds: int = 10,
        file_path: str = "network_log.json",
    ):
        self.driver.get(merge_url_query_params(URL, params))
        time.sleep(30)
        print("Starting to scroll...")
        page_height = self.driver.execute_script("return document.body.scrollHeight")
        for i in range(1, rounds):
            self.load_step(i, page_height)
        time.sleep(20)
        entries = self.save_network_logs(file_path=file_path)
        xlsx_path = (
            file_path.replace(".json", ".xlsx")
            if file_path.endswith(".json")
            else file_path + ".xlsx"
        )
        self.to_excel(entries=entries, file_path=xlsx_path)

    def __exit__(self, exception_type, exception_value, traceback) -> bool:
        self.driver.quit()
        return self.suppress
