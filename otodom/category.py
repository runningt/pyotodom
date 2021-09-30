#!/usr/bin/python
# -*- coding: utf-8 -*-

import logging
import sys
from bs4 import BeautifulSoup

from otodom import WHITELISTED_DOMAINS
from otodom.utils import get_response_for_url, get_url

if sys.version_info < (3, 3):
    from urlparse import urlparse
else:
    from urllib.parse import urlparse


log = logging.getLogger(__file__)


def parse_category_offer(offer_markup):
    """
    A method for getting the most important data out of an offer markup.

    :param offer_markup: a requests.response.content object
    :rtype: dict(string, string)
    :return: see the return section of :meth:`scrape.category.get_category` for more information
    """
    html_parser = BeautifulSoup(offer_markup, "html.parser")
    link = html_parser.find("a")
    url = link.attrs['href']
    if not url:
        # detail url is not present
        return {}
    offer_id = url.split("-")[-1]
    image = html_parser.find("img")
    image = image.get("src","").split(";")[0] or image.text
    title = html_parser.find("h3", {"data-cy":"listing-item-title"})
    title = title.text.strip() if title else ""
    poster = html_parser.find("span", class_="css-5zites es62z2j10") or html_parser.find("span", class_="css-acay6o es62z2j9")
    poster = poster.text.strip() if poster else ""
    price = html_parser.find("p", class_="css-lk61n3 es62z2j20")
    price = price.text.strip().replace('\xa0', ' ') if price else ""

    details = html_parser.findAll("span", class_="css-348r18 es62z2j21")
    if len(details) > 2:
        size = details[1].text.strip()
        rooms = details[0].text.strip()
        per_m2 = details[2].text.strip().replace('\xa0', ' ')
    else:
        size = ""
        rooms = ""
        per_m2 = ""


    return {
        'detail_url': url,
        'offer_id': offer_id,
        'poster': poster,
        'image': image,
        'price': price,
        'size': size,
        'rooms': rooms,
        'price_per_m2' : per_m2
    }


def parse_category_content(markup, get_promoted=False):
    """
    A method for getting a list of all the offers found in the markup.

    :param markup: a requests.response.content object
    :get_promoted: True if promoted offers should be added to results
    :rtype: list of parsed offers dicts
    """
    html_parser = BeautifulSoup(markup, "html.parser")
# TODO: get rid of promoted offers if required
#    search_listings = html_parser.findAll("div", {"data-cy":"search-listing"})
#    if len(search_listings) == 0:
#        return []

#    if not get_promoted:
#        if len(search_listings) > 1 :
#            search_listing = search_listings[1]
#        else:
#            search_listing = search_listings[0]
#        html_parser = BeautifulSoup(search_listing, "html.parser")
    offers = html_parser.findAll("a", {"data-cy":"listing-item-link"})
    parsed_offers = [
        parse_category_offer(str(offer)) for offer in offers
    ]
    return parsed_offers


def get_category_number_of_pages(markup):
    """
    A method that returns the maximal page number for a given markup, used for pagination handling.

    :param markup: a requests.response.content object
    :rtype: int
    """
    html_parser = BeautifulSoup(markup, "html.parser")
    pages = html_parser.findAll("button", {"data-cy":"pagination.go-to-page"})
    print(f"pages:{pages}")
    return int(pages.text) if pages else 1


def was_category_search_successful(markup):
    html_parser = BeautifulSoup(markup, "html.parser")
    has_warning = bool(html_parser.find(class_="search-location-extended-warning"))
    return not has_warning


def get_category_number_of_pages_from_parameters(main_category, detail_category, region, **filters):
    """A method to establish the number of pages before actually scraping any data"""
    url = get_url(main_category, detail_category, region, "400", 1, **filters)
    content = get_response_for_url(url).content
    if not was_category_search_successful(content):
        log.warning("Search for category wasn't successful", url)
        return 0
    html_parser = BeautifulSoup(content, "html.parser")
    offers = html_parser.find(class_="current")
    return int(offers.text) if offers else 1


def get_distinct_category_page(page, main_category, detail_category, region, **filters):
    """A method for scraping just the distinct page of a category"""
    parsed_content = []
    url = get_url(main_category, detail_category, region, "72", page, **filters)
    content = get_response_for_url(url).content

    parsed_content.extend(parse_category_content(content))

    return parsed_content


def get_category(main_category, detail_category, region, limit="400", **filters):
    """
    Scrape OtoDom search results based on supplied parameters.

    :param main_category: "wynajem" or "sprzedaz", should not be empty
    :param detail_category: "mieszkanie", "dom", "pokoj", "dzialka", "lokal", "haleimagazyny", "garaz", or
                            empty string for any
    :param region: a string that contains the region name. Districts, cities and voivodeships are supported. The exact
                    location is established using OtoDom's API, just as it would happen when typing something into the
                    search bar. Empty string returns results for the whole country. Will be ignored if either 'city',
                    'region', '[district_id]' or '[street_id]' is present in the filters.
    :param filters: the following dict contains every possible filter with examples of its values, but can be empty:

    ::

        input_dict = {
            '[dist]': 0,  # distance from region
            '[filter_float_price:from]': 0,  # minimal price
            '[filter_float_price:to]': 0,  # maximal price
            '[filter_float_price_per_m:from]': 0  # maximal price per square meter, only used for apartments for sale
            '[filter_float_price_per_m:to]': 0  # minimal price per square meter, only used for apartments for sale
            '[filter_enum_market][]': [primary, secondary]  # enum: primary, secondary
            '[filter_enum_building_material][]': []  # enum: brick, wood, breezeblock, hydroton, concrete_plate,
                concrete, silikat, cellular_concrete, reinforced_concrete, other, only used for apartments for sale
            '[filter_float_m:from]': 0,  # minimal surface
            '[filter_float_m:to]': 0,  # maximal surface
            '[filter_enum_rooms_num][]': '1',  # number of rooms, enum: from "1" to "10", or "more"
            '[private_business]': 'private',  # poster type, enum: private, business
            '[open_day]': 0,  # whether or not the poster organises an open day
            '[exclusive_offer]': 0,  # whether or not the offer is otodom exclusive
            '[filter_enum_rent_to_students][]': 0,  # whether or not the offer is aimed for students, only used for
                apartments for rent
            '[filter_enum_floor_no][]': 'floor_1',  # enum: cellar, ground_floor, floor_1-floor_10, floor_higher_10,
                garret
            '[filter_float_building_floors_num:from]': 1,  # minimal number of floors in the building
            '[filter_float_building_floors_num:to]': 1,  # maximal number of floors in the building
            'building_type': 'blok',  # enum: blok, w-kamienicy, dom-wolnostojacy, plomba, szeregowiec,
                apartamentowiec, loft
            '[filter_enum_heating][]': 'urban',  # enum: urban, gas, tiled_stove, electrical, boiler_room, other
            '[filter_float_build_year:from]': 1980,  # minimal year the building was built in
            '[filter_float_build_year:to]': 2016,  # maximal year the building was built in
            '[filter_enum_extras_types][]': ['balcony', 'basement'],  # enum: balcony, usable_room, garage, basement,
                garden, terrace, lift, two_storey, separate_kitchen, air_conditioning, non_smokers_only
            '[filter_enum_media_types][]': ['internet', 'phone'],  # enum: internet, cable-television, phone
            '[free_from]': 'from_now',  # when will it be possible to move in, enum: from_now, 30, 90
            '[created_since]': 1,  # when was the offer posted on otodom in days, enum: 1, 3, 7, 14
            '[id]': 48326376,  # otodom offer ID, found at the very bottom of each offer
            'description_fragment': 'wygodne',  # the resulting offers' descriptions must contain this string
            '[photos]': 0,  # whether or not the offer contains photos
            '[movie]': 0,  # whether or not the offer contains video
            '[walkaround_3dview]': 0  # whether or not the offer contains a walkaround 3D view
            'city':  # lowercase, no diacritics, '-' instead of spaces, _city_id at the end
            'voivodeship':  # lowercase, no diacritics, '-' instead of spaces
            '[district_id]': from otodom API
            '[street_id]': from otodom API
        }

    :rtype: list of dict(string, string)
    :return: Each of the dictionaries contains the following fields:

    ::

        'detail_url' - a link to the offer
        'offer_id' - the internal otodom's offer ID, not to be mistaken with the '[id]' field from the input_dict
        'poster' - a piece of information about the poster. Could either be a name of the agency or "Oferta prywatna"
    """
    page, pages_count, parsed_content = 1, None, []

    while page == 1 or page <= pages_count:
        url = get_url(main_category, detail_category, region, limit, page, **filters)
        content = get_response_for_url(url).content
        if not was_category_search_successful(content):
            log.warning("Search for category wasn't successful", url)
            return []

        parsed_content.extend(parse_category_content(content))

        if page == 1:
            pages_count = get_category_number_of_pages(content)
            if page == pages_count:
                break

        page += 1

    return parsed_content
