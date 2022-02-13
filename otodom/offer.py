#!/usr/bin/python
# -*- coding: utf-8 -*-

import datetime as dt
import json
import logging
import re

import requests
from bs4 import BeautifulSoup
from scrapper_helpers.utils import _float, _int, caching, get_random_user_agent, key_sha1, replace_all

from otodom import BASE_URL
from otodom.utils import _rooms_translate, get_cookie_from, get_csrf_token, get_response_for_url, price_to_float

log = logging.getLogger(__file__)


def parse_json_offer(offer):

    slug_id = offer.get("slug", "")
    detail_url = "/".join([BASE_URL, "pl", "oferta", slug_id])
    offer_id = slug_id.split("-")[-1]
    try:
        image_url = offer["images"][0]["large"]
    except (IndexError, AttributeError):
        image_url = ""

    try:
        # TODO: calculate to PLN if different currency
        if offer["totalPrice"]["currency"] != "PLN":
            price = -1.0
        else:
            price = offer["totalPrice"]["value"]
            if isinstance(price, str):
                price = price_to_float(price)

    except (IndexError, AttributeError, TypeError):
        price = -1.0

    try:
        # TODO: calculate to PLN if different currency
        if offer["pricePerSquareMeter"]["currency"] != "PLN":
            price_per_m2 = -1.0
        else:
            price_per_m2 = offer["pricePerSquareMeter"]["value"]
            if isinstance(price_per_m2, str):
                price_per_m2 = price_to_float(price_per_m2)
    except (IndexError, AttributeError, TypeError):
        price_per_m2 = -1.0

    try:
        rooms = _rooms_translate.get(offer["roomsNumber"], 0)
    except (IndexError, AttributeError):
        rooms = 0
    size = offer.get("areaInSquareMeters", 0)

    return {
        "detail_url": detail_url,
        "offer_id": offer_id,
        "int_id": offer["id"],
        # 'poster': poster,
        image_url: image_url,
        "price": price,
        "price_int": round(price),
        "size": size,
        "rooms": rooms,
        "rooms_label": offer.get("roomsNumber", ""),
        "price_per_m2": price_per_m2,
        "calculated_per_m2": price / size if size else -1.0,
        "offer_info": offer,
    }

    return json_offer


def parse_category_offer(offer_markup):
    """
    A method for getting the most important data out of an offer markup.

    :param offer_markup: a requests.response.content object
    :rtype: dict(string, string)
    :return: see the return section of :meth:`scrape.category.get_category` for more information

    TODO: "Adjust to new otodom version"
    """
    html_parser = BeautifulSoup(offer_markup, "html.parser")
    link = html_parser.find("a")
    url = link.attrs["href"]
    if not url:
        # detail url is not present
        return {}
    offer_id = url.split("-")[-1]
    url = BASE_URL + url
    image = html_parser.find("img")
    image = image.get("src", "").split(";")[0] or image.text if image else ""
    article = html_parser.find("article")
    title = article.find("h3", {"data-cy": "listing-item-title"})
    title = title.text.strip() if title else ""
    data = article.findAll("p")
    price = price_to_float(data[1].text)
    size = ""
    rooms = ""
    per_m2 = ""
    try:
        details = data[2]
        details = details.findAll("span")
        if len(details) > 2:
            rooms = "".join(filter(str.isdigit, details[0].text))
            size = price_to_float(details[1].text)
            per_m2 = price_to_float(details[2].text)
    except IndexError:
        pass

    # TODO: add poster
    # posters = article.find("div/span")
    # if len(posters)> 2:
    #    poster = posters[1].text if posters[1].text else posters[2].text or ""
    # else:
    #   poster = ""
    return {
        "detail_url": url,
        "offer_id": offer_id,
        # 'poster': poster,
        "image": image,
        "price": price,
        "price_int": round(price),
        "size": size,
        "rooms": rooms,
        "price_per_m2": per_m2,
        "calculated_per_m2": price / size if size else -1,
    }


@caching(key_func=key_sha1)
def get_offer_phone_numbers(offer_id, cookie, csrf_token):
    """
    This method makes a request to the OtoDom API asking for the poster's phone number(s) and returns it.

    :param offer_id: string, taken from context, see the return section of :meth:`scrape.category.get_category` for
                    reference
    :param cookie: string, see :meth:`scrape.utils.get_cookie_from` for reference
    :param csrf_token: string, see :meth:`scrape.utils.get_csrf_token` for reference
    :rtype: list(string)
    :return: A list of phone numbers as strings (no spaces, no '+48')
    """
    url = "https://www.otodom.pl/ajax/misc/contact/phone/{0}/".format(offer_id)
    payload = "CSRFToken={0}".format(csrf_token)
    headers = {
        "cookie": "{0}".format(cookie),
        "content-type": "application/x-www-form-urlencoded",
        "User-Agent": get_random_user_agent(),
    }

    response = requests.request("POST", url, data=payload, headers=headers)
    if response.status_code == 404:
        return []
    return json.loads(response.text)["value"]


def get_offer_facebook_description(html_parser):
    """
    This method returns the short standardized description used for the default facebook share message.

    :param html_parser: a BeautifulSoup object
    :rtype: string
    :return: The default facebook share message
    """
    fb_description = html_parser.find(attrs={"name": "description"}).attrs["content"]
    return fb_description


def get_offer_ninja_pv(html_content):
    """
    This method returns the website's ninjaPV json data as dict.

    :param html_content: a requests.response.content object
    :rtype: dict
    :return: ninjaPV data
    """
    found = re.search(
        r".*window\.ninjaPV\s=\s(?P<json_info>{.*?})",
        html_content.decode("unicode-escape"),
    )
    ninja_pv = found.groupdict().get("json_info")
    return json.loads(ninja_pv)


def get_offer_floor(html_parser):
    """
    This method returns the floor on which the apartment is located.

    :param html_parser: a BeautifulSoup object
    :rtype: string
    :return: The floor number
    """
    floor_number_raw_data = html_parser.find(class_="param_floor_no")
    floor = ""
    if hasattr(floor_number_raw_data, "strong"):
        floor = floor_number_raw_data.strong.text
    return "0" if floor == "parter" else floor


def get_offer_total_floors(html_parser, default_value=""):
    """
    This method returns the maximal number of floors in the building.

    :param html_parser: a BeautifulSoup object
    :rtype: string
    :return: The maximal floor number
    """
    # searching dom for floor data
    floor_raw_data = html_parser.find(class_="param_floor_no")
    if hasattr(floor_raw_data, "span"):
        floor_data = floor_raw_data.span.text
    else:
        return default_value
    # extracting information about floor
    match = re.search(r"\w+\s(?P<total>\d+)", floor_data)
    total_floors = default_value
    if match:
        total_floors = match.groupdict().get("total")
    return total_floors


def get_month_num_for_string(value):
    """
    Map for polish month names

    :param value: Month value
    :type value: str
    :return: Month number
    :rtype: int
    """
    value = value.lower()[:3]
    return {
        "sty": 1,
        "lut": 2,
        "mar": 3,
        "kwi": 4,
        "maj": 5,
        "cze": 6,
        "lip": 7,
        "sie": 8,
        "wrz": 9,
        "paź": 10,
        "lis": 11,
        "gru": 12,
    }.get(value)


def parse_available_from(date):
    """
    Parses string date to unix timestamp

    :param date: Date
    :type date: str
    :return: Unix timestamp
    :rtype: int
    """
    date_parts = date.split(" ")
    month = get_month_num_for_string(date_parts[1].lower())
    year = int(date_parts[2])
    day = int(date_parts[0])
    date_added = dt.datetime(year=year, day=day, month=month)
    return int((date_added - dt.datetime(1970, 1, 1)).total_seconds())


def get_offer_apartment_details(html_parser):
    """
    This method returns detailed information about the apartment.

    :param html_parser: a BeautifulSoup object
    :rtype: list(dict)
    :return: A list containing dictionaries of details, for example {'kaucja': 1100 zł}
    """
    found = html_parser.find(class_="sub-list")
    apartment_details = ""
    if found:
        apartment_details = found.text
    details = [
        {d.split(": ")[0]: d.split(": ")[1]}
        for d in str(apartment_details).split("\n")
        if d
    ]
    for i, detail in enumerate(details):
        available_from = detail.get("Dostępne od")
        if available_from:
            details[i] = {list(detail.keys())[0]: parse_available_from(available_from)}
    return details


def get_offer_additional_assets(html_parser):
    """
    This method returns information about the apartment's additional assets.

    :param html_parser: a BeautifulSoup object
    :rtype: list(string)
    :return: A list containing the additional assets
    """
    additional_group_assets = html_parser.findAll(class_="dotted-list")
    assets = []
    if additional_group_assets:
        assets = [
            asset.strip()
            for group in additional_group_assets
            for asset in group.text.split("\n")
            if asset
        ]
    return assets


def get_offer_description(html_parser):
    """
    This method returns the apartment description.

    :param html_parser: a BeautifulSoup object
    :rtype: string
    :return: The apartment description
    """
    element = html_parser.find(itemprop="description") or html_parser.find(
        class_="offer-description"
    )
    if not element:
        return
    description = element.text.replace("\xa0", " ").replace("\n", " ")
    return description


def get_offer_poster_name(html_parser):
    """
    This method returns the poster's name (and surname if available).

    :param html_parser: a BeautifulSoup object
    :rtype: string
    :return: The poster's name
    """
    element = html_parser.find(class_="box-person-name") or html_parser.find(
        class_="seller-box__seller-name"
    )
    if not element:
        return
    name = element.text.strip()
    return name


def get_offer_photos_links(html_parser):
    """
    This method returns a list of links to photos of the apartment.

    :param html_parser: a BeautifulSoup object
    :rtype: list(string)
    :return: A list of links to photos of the apartment
    """
    gallery = html_parser.findAll(class_="gallery-box-thumb-item")
    return [p.attrs["href"] for p in gallery]


def get_offer_video_link(html_parser):
    """
    This method returns a link to a video of the apartment.

    :param html_parser: a BeautifulSoup object
    :rtype: string
    :return: A link to a video of the apartment
    """
    video_raw_data = html_parser.find(class_="section-offer-video")
    video = ""
    if hasattr(video_raw_data, "iframe"):
        video = html_parser.find(class_="section-offer-video").iframe.attrs["src"]
    return video


def get_offer_3d_walkaround_link(html_parser):
    """
    This method returns a link to a 3D walkaround view of the apartment.

    :param html_parser: a BeautifulSoup object
    :rtype: string
    :return: A 3D walkaround view of the apartment
    """
    walkaround_raw_data = walkaround = html_parser.find(
        "strong", string="wirtualny spacer:"
    )
    walkaround = ""
    if hasattr(walkaround_raw_data, "strong"):
        walkaround = html_parser.find(
            "strong", string="wirtualny spacer:"
        ).next_sibling.next_sibling.attrs["href"]
    return walkaround


def get_offer_geographical_coordinates(html_parser):
    """
    This method returns the geographical coordinates of the apartment.

    :param html_parser: a BeautifulSoup object
    :rtype: tuple(string)
    :return: A tuple containing the latitude and longitude of the apartment
    """
    try:
        latitude = _float(html_parser.find(itemprop="latitude").attrs["content"])
        longitude = _float(html_parser.find(itemprop="longitude").attrs["content"])
    except AttributeError:
        latitude, longitude = None, None
    return latitude, longitude


def parse_date_to_timestamp(date):
    """
    Parses string date to unix timestamp

    :param date: Date
    :type date: str
    :return: Unix timestamp
    :rtype: int
    """
    if "ponad" in date:
        date = (dt.datetime.now() - dt.timedelta(days=15)).date().strftime("%d.%m.%Y")
    date_parts = date.split(".")
    month = int(date_parts[1])
    year = int(date_parts[2])
    day = int(date_parts[0])
    date_added = dt.datetime(year=year, day=day, month=month)
    return int((date_added - dt.datetime(1970, 1, 1)).total_seconds())


def get_offer_details(html_parser):
    """
    This method returns detailed information about the offer.

    :param html_parser: a BeautifulSoup object
    :rtype: list(dict)
    :return: A list of dictionaries containing information about the offer
    """
    # [{d.split(': ')[0].strip(): d.split(': ')[1].strip()} for d in f.split("\n") if not re.match(r'^\s*$', d)]
    try:
        f = html_parser.find(class_="text-details").text
        temp = [d for d in f.split("\n") if not re.match(r"^\s*$", d)]
        output = [
            {d.split(": ")[0].strip(): d.split(": ")[1].strip()}
            for d in temp
            if "Data" not in d
        ]
        output.extend(
            [
                {
                    d.split(": ")[0].strip(): parse_date_to_timestamp(
                        d.split(": ")[1].strip()
                    )
                }
                for d in temp
                if "Data" in d
            ]
        )
        return output
    except AttributeError:
        return {}


def get_offer_title(html_parser):
    """
    This method returns the offer title.

    :param html_parser: a BeautifulSoup object
    :rtype: string
    :return: The offer title
    """
    title = html_parser.find("meta", attrs={"property": "og:title"})["content"]
    return title


def get_offer_address(html_parser):
    """
    This method returns the offer address.

    :param html_parser: a BeautifulSoup object
    :rtype: string
    :return: The offer address
    """
    try:
        address = html_parser.find(class_="address-text").text
    except AttributeError:
        return
    else:
        return address


def build_offer_additonal_assets(additional_assets, apartment_details):
    details = {k: v for d in apartment_details for k, v in d.items()}
    if not any(details.values()):
        return {}

    return {
        "heating": details.get("ogrzewanie"),
        "balcony": "balkon" in additional_assets,
        "kitchen": "oddzielna kuchnia" in additional_assets,
        "terrace": "taras" in additional_assets,
        "internet": "internet" in additional_assets,
        "elevator": "winda" in additional_assets,
        "car_parking": "garaż/miejsce parkingowe" in additional_assets,
        "disabled_facilities": None,
        "mezzanine": None,
        "basement": "winda" in additional_assets,
        "duplex_apartment": "dwupoziomowe" in additional_assets,
        "garden": "ogródek" in additional_assets,
        "garage": "garaż" in "garaż/miejsce parkingowe" in additional_assets,
        "cable_tv": "telewizja kablowa" in details,
    }


def get_flat_data(html_parser, ninja_pv):
    apartment_details = get_offer_apartment_details(html_parser)

    return {
        "3D_walkaround_link": get_offer_3d_walkaround_link(html_parser),
        "apartment_details": apartment_details,
        "additional_assets": build_offer_additonal_assets(
            get_offer_additional_assets(html_parser), apartment_details
        ),
        "surface": _float(ninja_pv.get("surface", "")),
        "rooms": _int(ninja_pv.get("rooms", "")),
        "floor": _int(get_offer_floor(html_parser)),
        "total_floors": _int(get_offer_total_floors(html_parser)),
    }


def get_offer_information(url, context=None):
    """
    Scrape detailed information about an OtoDom offer.

    :param url: a string containing a link to the offer
    :param context: a dictionary(string, string) taken straight from the :meth:`scrape.category.get_category`

    :returns: A dictionary containing the scraped offer details
    """
    # TODO: Fix this one also
    # getting response
    return {}
    response = get_response_for_url(url)
    content = response.content
    html_parser = BeautifulSoup(content, "html.parser")
    # getting meta values
    if context:
        cookie = get_cookie_from(response)
        try:
            csrf_token = get_csrf_token(content)
            offer_id = context["offer_id"]
        except AttributeError:
            csrf_token = ""
            offer_id = ""

        # getting offer details
        try:
            phone_numbers = get_offer_phone_numbers(offer_id, cookie, csrf_token)
        except KeyError:
            # offer was not present any more
            phone_numbers = []

        phone_number_replace_dict = {"\xa0": "", " ": "", "-": "", "+48": ""}
        phone_numbers = sum(
            [
                replace_all(num, phone_number_replace_dict).split(".")
                for num in phone_numbers
            ],
            [],
        )
    else:
        cookie = ""
        csrf_token = ""
        phone_numbers = ""
        context = {}

    ninja_pv = get_offer_ninja_pv(content)
    result = {
        "title": get_offer_title(html_parser),
        "address": get_offer_address(html_parser),
        "poster_name": get_offer_poster_name(html_parser),
        "poster_type": ninja_pv.get("poster_type"),
        "price": ninja_pv.get("ad_price"),
        "currency": ninja_pv.get("price_currency"),
        "city": ninja_pv.get("city_name"),
        "district": ninja_pv.get("district_name", ""),
        "voivodeship": ninja_pv.get("region_name"),
        "geographical_coordinates": get_offer_geographical_coordinates(html_parser),
        "phone_numbers": phone_numbers,
        "description": get_offer_description(html_parser),
        "offer_details": get_offer_details(html_parser),
        "photo_links": get_offer_photos_links(html_parser),
        "video_link": get_offer_video_link(html_parser),
        "facebook_description": get_offer_facebook_description(html_parser),
        "meta": {"cookie": cookie, "csrf_token": csrf_token, "context": context},
    }

    flat_data = get_flat_data(html_parser, ninja_pv)
    if any(flat_data.values()):
        result.update(flat_data)
    return result
