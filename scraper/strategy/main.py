import abc
import json
import logging
from typing import Dict, Iterable, List, Literal, Tuple, TypedDict, Union
import pandas as pd


class Entry(TypedDict):
    startedDateTime: str
    time: float
    request: Dict[str, Union[str, int, None, List[Dict[str, Union[str, int, None]]]]]
    response: Dict[str, Union[str, int, None, List[Dict[str, Union[str, int, None]]]]]
    cache: Dict[str, Union[str, int, None]]
    timings: Dict[str, Union[str, int, None]]
    serverIPAddress: str


class BaseStrategy(abc.ABC):
    strategy: str
    data: Entry

    def __init__(self, data: Union[Entry, str]):
        if isinstance(data, str):
            data: Entry = json.loads(data)
        self.data = data

    @abc.abstractmethod
    def parse(self) -> Entry:
        """Parses the entry

        Returns:
            Entry: the parsed entry
        """
        pass

    @abc.abstractmethod
    def validate(self) -> bool:
        """Validates if, for a given strategy, the entry is valid

        Returns:
            bool: True if the entry is valid, False otherwise
        """
        pass


class GraphQlStrategy(BaseStrategy):
    strategy = "graphql"

    def _mime_type_valid(self):
        return self.data["response"]["content"]["mimeType"].startswith("text/html")

    def _url_valid(self):
        url = self.data["request"]["url"]
        return url.startswith("https://www.facebook.com/api/graphql")

    def _object_valid(self) -> str:
        try:
            if isinstance(self.data["response"]["content"]["text"], dict):
                return True
            json.loads(self.data["response"]["content"]["text"])
            return True
        except Exception as e:
            logging.info("_object_valid")
            logging.info(self.data["response"]["content"]["text"])
            logging.error(e)
            return False

    def _has_valid_parameters(self):
        return self._url_valid() and self._mime_type_valid() and self._object_valid()

    def parse(self) -> Entry:
        if isinstance(self.data["response"]["content"]["text"], dict):
            return self.data
        json_text = json.loads(self.data["response"]["content"]["text"])
        self.data["response"]["content"]["text"] = json_text
        return self.data

    def validate(self) -> bool:
        """Validates if, for a given strategy, the entry is valid

        Returns:
            bool: True if the entry is valid, False otherwise
        """
        return True if self._has_valid_parameters() else False


class SearchAdsStrategy(BaseStrategy):
    strategy = "search_ads"

    def _mime_type_valid(self):
        return self.data["response"]["content"]["mimeType"].startswith(
            "application/x-javascript"
        )

    def _url_valid(self):
        url = self.data["request"]["url"]
        return url.startswith("https://www.facebook.com/ads/library/async/search_ads/")

    def _object_valid(self) -> str:
        try:
            text = self.data["response"]["content"]["text"]
            if isinstance(text, dict):
                return True
            if not text.startswith("for (;;);"):
                return False
            json.loads(text.replace("for (;;);", ""))
            return True
        except Exception as e:
            logging.info(text)
            logging.error(e)
            return False

    def _has_valid_parameters(self):
        return self._url_valid() and self._mime_type_valid() and self._object_valid()

    def parse(self) -> Entry:
        text = self.data["response"]["content"]["text"]
        if isinstance(text, dict):
            return self.data
        json_text = json.loads(text.replace("for (;;);", ""))
        self.data["response"]["content"]["text"] = json_text
        return self.data

    def validate(self) -> bool:
        """Validates if, for a given strategy, the entry is valid

        Returns:
            bool: True if the entry is valid, False otherwise
        """
        return True if self._has_valid_parameters() else False


class Executor:
    def __init__(
        self, strategies: List[BaseStrategy] = [GraphQlStrategy, SearchAdsStrategy]
    ):
        self.strategies = strategies

    def execute(
        self, entries: List[Entry]
    ) -> Iterable[Tuple[Entry, Literal["search_ads", "graphql", ""]]]:
        for entry in entries:
            for Strategy in self.strategies:
                strategy: BaseStrategy = Strategy(data=entry)
                try:
                    url = strategy.data["request"]["url"]
                    # has_url = url.startswith("https://www.facebook.com/api/graphql")
                    # if has_url and strategy._url_valid():
                    #     print(strategy._mime_type_valid())
                    #     print(strategy._url_valid())
                    #     print(strategy._object_valid())
                    if strategy._url_valid() and strategy.validate():
                        parsed_entry = strategy.parse()
                        yield (parsed_entry, strategy.strategy)
                except Exception as e:
                    logging.error(e)
                    yield ([], "")

    def save(self, entries: List[Entry], file_path: str):
        data = {"search_ads": [], "graphql": []}
        with open(file_path, "w") as f:
            for entry, strategy in self.execute(entries):
                if strategy:
                    data[strategy].append(entry)
            f.write(json.dumps(data))

    def to_excel(self, entries: List[Entry], file_path: str, threshold: int = 30):
        search_ads = pd.DataFrame(
            [],
            [
                "collationCount",
                "isActive",
                "pageID",
                "pageName",
                "pageIsDeleted",
                "ad_creative_id",
                "title",
            ],
        )
        for entry, strategy in self.execute(entries):
            if strategy:
                if strategy == "search_ads":
                    results = entry["response"]["content"]["text"]["payload"]["results"]
                    if results is not None and len(results) > 0:
                        for result in results:
                            if len(result) > 0:
                                for r in result:
                                    ad_archive_id = r.get("adArchiveID", "")
                                    page_id = r.get("pageID", "")
                                    url = f"https://www.facebook.com/ads/library/?active_status=all&ad_type=political_and_issue_ads&country=BR&id={ad_archive_id}&view_all_page_id={page_id}&search_type=page&media_type=all"
                                    collation_count = (
                                        int(r.get("collationCount", 0))
                                        if r.get("collationCount", 0) is not None
                                        else 0
                                    )
                                    base_data = {
                                        "collationCount": collation_count,
                                        "isActive": r.get("isActive", False),
                                        "pageID": r["pageID"],
                                        "pageName": r["pageName"],
                                        "pageIsDeleted": r["pageIsDeleted"],
                                        "ad_url": url,
                                    }
                                    snapshots = r["snapshot"]
                                    if (
                                        collation_count is None
                                        or collation_count < threshold
                                    ):
                                        continue
                                    if "ad_creative_id" in snapshots:
                                        page_categories = snapshots.get(
                                            "page_categories", {}
                                        )
                                        categories = list(page_categories.values())
                                        parsed_categories = "".join(
                                            str(x) for x in categories
                                        )
                                        base_snapshot = {
                                            "ad_creative_id": snapshots[
                                                "ad_creative_id"
                                            ],
                                            "page_categories": parsed_categories,
                                            "caption": snapshots.get("caption", ""),
                                        }
                                        cards = snapshots.get("cards", [])
                                        if cards is not None and len(cards) > 0:
                                            for card in cards:
                                                if "title" in card:
                                                    base_card = {
                                                        "title": card.get("title", ""),
                                                        "body": card.get("body", ""),
                                                        "link": card.get(
                                                            "link_url", ""
                                                        ),
                                                    }
                                                    frame = {
                                                        **base_card,
                                                        **base_snapshot,
                                                        **base_data,
                                                    }
                                                    search_ads = pd.concat(
                                                        [
                                                            search_ads,
                                                            pd.DataFrame([frame]),
                                                        ]
                                                    )
        search_ads.to_excel(file_path, index=False)
