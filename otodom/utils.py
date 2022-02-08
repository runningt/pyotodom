# .!/usr/bin/python
# -*- coding: utf-8 -*-

import json
import logging
import re
import sys

import requests

try:
    from __builtin__ import unicode
except ImportError:
    unicode = lambda x, *args: x

from bs4 import BeautifulSoup
from scrapper_helpers.utils import (
    caching,
    get_random_user_agent,
    key_sha1,
    normalize_text,
)

from otodom import BASE_URL

if sys.version_info < (3, 2):
    from urllib import quote
else:
    from urllib.parse import quote

REGION_DATA_KEYS = ["city", "voivodeship", "district_id", "street_id"]

log = logging.getLogger(__file__)


@caching(key_func=key_sha1)
def get_region_from_autosuggest(region_part):
    """
    This method makes a request to the OtoDom api, asking for the best fitting region for the supplied
    region_part string.

    :param region_part: input string, it should be a part of an existing region in Poland, either city, street,
                        district or voivodeship
    :rtype: dict
    :return: A dictionary which contents depend on the API response.
    """
    if not region_part:
        return {}
    url = f"{BASE_URL}/ajax/geo6/autosuggest/?data={normalize_text(region_part, lower=False, replace_spaces='')}"
    response = json.loads(get_response_for_url(url).text)[0]
    region_type = response["level"]
    text = response["text"].replace("<strong>", "").replace("</strong>", "").split(", ")

    region_dict = {}

    if region_type == "CITY":
        region_dict["city"] = response["name"]
        region_dict["id"] = response["id"].replace(".", "/")
    elif region_type == "DISTRICT":
        region_dict["city"] = response["name"]
        region_dict["districtId"] = response["district_id"]
        region_dict["id"] = response["id"].replace(".", "/")
    elif region_type == "REGION":
        region_dict["voivodeship"] = normalize_text(text[0])
        region_dict["regionId"] = response["region_id"]
        region_dict["id"] = response["id"].replace(".", "/")
    elif region_type == "STREET":
        region_dict["city"] = normalize_text(text[0].split(",")[0])
        region_dict["streetId"] = response["street_id"]
        # TODO: concert id in format region.subregion.district.s.street into url
        region_dict["id"] = response["id"].split(".s")[0].replace(".", "/")
    return region_dict


def get_region_from_filters(filters):
    """
    This method does a similiar thing as :meth:`scrape.utils.get_region_from_autosuggest` but instead of calling the
    API, it uses the data provided in the filters

    :param filters: dict, see :meth:`scrape.category.get_category` for reference
    :rtype: dict
    :return: A dictionary which contents depend on the filters content.
    """
    # TODO: Adjust to new format
    region_dict = {
        region_data: filters.get(region_data)
        for region_data in REGION_DATA_KEYS
        if region_data in filters
    }
    return region_dict


def _float(number, default=None):
    return get_number_from_string(number, float, default)


def _int(number, default=None):
    return get_number_from_string(number, int, default)


def get_number_from_string(s, number_type, default):
    try:
        return number_type(s.replace(",", "."))
    except ValueError:
        return default


def price_to_float(price: str) -> float:
    filtered = "".join(
        d for d in price if d.isdigit() and d.isascii() or d in [",", "."]
    )
    return _float(filtered, default=0.0)


def get_url(
    main_category, detail_category, region_data, limit="24", page="1", **filters
):
    """
    This method builds a ready-to-use url based on the input parameters.

    :param main_category: see :meth:`scrape.category.get_category` for reference
    :param detail_category: see :meth:`scrape.category.get_category` for reference
    :param region_data: see :meth:`scrape.utils.get_region_from_autosuggest` for reference
    :param limit: num of ads per page, 400 can be used to lower the amount of requests
    :param page: page number
    :param filters: see :meth:`scrape.category.get_category` for reference
    :rtype: string
    :return: the url"""

    if "districtId" in region_data:
        filters["districtId"] = region_data["districtId"]

    if "streetId" in region_data:
        filters["streetId"] = region_data["streetId"]

    # creating base url
    url = "/".join(
        [BASE_URL, "pl", "oferty", main_category, detail_category, region_data["id"]]
    )

    # adding building type if exists in filters
    if "building_type" in filters:
        url = url + "/" + filters["building_type"]

    # adding description fragment search if exists in filters
    if "description_fragment" in filters:
        url = url + "/q-" + "-".join(filters["description_fragment"].split())

    # preparing the rest of filters for addition to the url
    filter_list = []
    for key, value in filters.items():
        if isinstance(value, list):
            filter_list.append(f"{key}=[{','.join(value)}]")
        else:
            filter_list.append("{}={}".format(quote(key), value))

    url = f"{url}?limit={limit}&page={page}&" + "&".join(filter_list)
    log.info(url)
    return url


@caching(key_func=key_sha1)
def _get_json_identifier(main_category, detail_category, region_data, **filters):
    """
    get identifier from buildMaifest
    """
    short_url = get_url(main_category, detail_category, region_data, 1, 1, **filters)
    content = BeautifulSoup(get_response_for_url(short_url).content, "html.parser")
    try:
        script = content.find("script", {"src": re.compile(r"buildManifest\.js")})
        return script.attrs["src"].split("/")[-2]
    except (IndexError, TypeError):
        return None


def get_json_url(
    main_category, detail_category, region_data, limit="24", page="1", **filters
):
    """
    Get url of json file with otodom search data
    """
    identifier = _get_json_identifier(
        main_category, detail_category, region_data, **filters
    )
    if not identifier:
        return None
    url = "/".join(
        [
            BASE_URL,
            "_next",
            "data",
            identifier,
            "pl",
            "oferty",
            main_category,
            detail_category,
            region_data["id"] + ".json",
        ]
    )

    # adding building type if exists in filters
    if "building_type" in filters:
        url = url + "/" + filters["building_type"]

    # adding description fragment search if exists in filters
    if "description_fragment" in filters:
        url = url + "/q-" + "-".join(filters["description_fragment"].split())

    # preparing the rest of filters for addition to the url
    filter_list = []
    for key, value in filters.items():
        if isinstance(value, list):
            filter_list.append(f"{key}=[{','.join(value)}]")
        else:
            filter_list.append("{}={}".format(quote(key), value))

    url = f"{url}?limit={limit}&page={page}&" + "&".join(filter_list)
    log.info(url)
    return url


def get_num_offers_from_markup(markup):
    """
    Get total number of offers scrapping page
    """
    # TODO: does not seem to work
    html_parser = BeautifulSoup(markup, "html.parser")
    num_offers = html_parser.find(
        "strong", {"data-cy": "search.listing-panel.label.ads-number"}
    )
    try:
        return int(num_offers.findAll("span")[-1].text)
    except ValueError:
        return 0


_main_category_translate = {
    "mieszkanie": "FLAT",
    "dom": "HOUSE",
    "pokoj": "ROOM",
    "dzialka": "TERRAIN",
    "lokal": "COMMERCIALPROPERTY",
    "haleimagazyny": "HALL",
    "garaz": "GARAGE",
}

_rooms_translate = {
    "ONE": 1,
    "TWO": 2,
    "THREE": 3,
    "FOUR": 4,
    "FIVE": 5,
    "SIX": 6,
    "SEVEN": 7,
    "EIGHT": 8,
    "NINE": 9,
    "TEN": 10,
}


def get_number_of_offers(main_category, detail_category, region_data, **filters):
    """
    Get number of offers from otodom internal REST API (https://otodom.pl/api/query) POST request

    :param main_category: see :meth:`scrape.category.get_category` for reference
    :param detail_category: see :meth:`scrape.category.get_category` for reference
    :param region_data: see :meth:`scrape.utils.get_region_from_autosuggest` for reference
    :param filters: see :meth:`scrape.category.get_category` for reference
    :rtype: int
    :return: number of offers, or -1 if failed

    """
    url = "/".join([BASE_URL, "api", "query"])

    filter_attributes = {
        "estate": _main_category_translate.get(main_category, "FLAT"),
        "transaction": "RENT" if detail_category == "wynajem" else "SELL",
    }
    filter_attributes.update(filters)

    region_attrs = region_data.get("id", "").split("/")
    geo_attributes = {
        "regionId": region_attrs[0] if len(region_attrs) > 0 else 0,
        "subregionId": region_attrs[1] if len(region_attrs) > 1 else 0,
        "cityId": region_attrs[2] if len(region_attrs) > 2 else 0,
        "streetId": region_data.get("streetId", 0),
        "districtId": region_data.get("districtId", 0),
    }

    body = {
        "query": "query GetCountAds($filterAttributes: FilterAttributes, $filterLocations: FilterLocations) {\n  countAds(filterAttributes: $filterAttributes, filterLocations: $filterLocations) {\n    ... on CountAds {\n      count\n      __typename\n    }\n    __typename\n  }\n}\n",
        "operationName": "GetCountAds",
        "variables": {
            "filterAttributes": filter_attributes,
            "filterLocations": {"byGeoAttributes": [geo_attributes]},
        },
    }
    result = requests.post(url, json=body)
    try:
        if result.status_code == 200:
            data = result.json().get("data", {})
            return data.get("countAds", {}).get("count", 0)
        else:
            return -1
    except ValueError:
        return -1


@caching(key_func=key_sha1)
def get_response_for_url(url):
    """
    :param url: an url, most likely from the :meth:`scrape.utils.get_url` method
    :return: a requests.response object
    """
    return requests.get(url, headers={"User-Agent": get_random_user_agent()})


def get_cookie_from(response):
    """
    :param response: a requests.response object
    :rtype: string
    :return: cookie information as string
    """
    cookie = response.headers["Set-Cookie"].split(";")[0]
    return cookie


def get_csrf_token(html_content):
    """
    :param html_content: a requests.response.content object
    :rtype: string
    :return: the CSRF token as string
    """
    found = re.match(
        r".*csrfToken\s+=(\\|\s)+'(?P<csrf_token>\w+).*", str(html_content)
    )
    csrf_token = found.groupdict().get("csrf_token")
    return csrf_token
