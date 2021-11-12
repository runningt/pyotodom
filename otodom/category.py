#!/usr/bin/python
# -*- coding: utf-8 -*-

import logging
import sys

from bs4 import BeautifulSoup

from otodom import BASE_URL
from otodom.utils import (
    get_number_from_string, get_number_of_offers, get_region_from_autosuggest, get_response_for_url, get_url,
    price_to_float
)

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
    url = link.attrs["href"]
    if not url:
        # detail url is not present
        return {}
    offer_id = url.split("-")[-1]
    url = BASE_URL + url
    image = html_parser.find("img")
    image = image.get("src", "").split(";")[0] or image.text if image else ''
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
        "calculated_per_m2": price / size if size else 0.0,
    }


def parse_category_content(markup, get_promoted=False):
    """
    A method for getting a list of all the offers found in the markup.

    :param markup: a requests.response.content object
    :get_promoted: True if promoted offers should be added to results
    :rtype: list of parsed offers dicts
    """
    html_parser = BeautifulSoup(markup, "html.parser")

    search_listings = html_parser.findAll("div", {"data-cy": "search.listing"})
    if len(search_listings) > 1:
        if not get_promoted:
            listing = search_listings[1]
        else:
            listing = html_parser
    elif len(search_listings) == 1:
        listing = search_listings[0]
    else:
        return []

    offers = listing.findAll("a", {"data-cy": "listing-item-link"})
    parsed_offers = [parse_category_offer(str(offer)) for offer in offers]
    return parsed_offers


def was_category_search_successful(markup):
    """
    :rtype: bool
    :return: True if search was successful, False if no results found
    """
    html_parser = BeautifulSoup(markup, "html.parser")
    has_warning = bool(html_parser.find("div", {"data-cy": "no-search-results"}))
    return not has_warning


def get_category(
    main_category, detail_category, region, offers_per_page="500", limit=0, **filters
):
    """
    Scrape OtoDom search results based on supplied parameters.

    :param main_category: "wynajem" or "sprzedaz", should not be empty
    :param detail_category: "mieszkanie", "dom", "pokoj", "dzialka", "lokal", "haleimagazyny", "garaz", or
                            empty string for any
    :param region: a string that contains the region name. Districts, cities and voivodeships are supported. The exact
                    location is established using OtoDom's API, just as it would happen when typing something into the
                    search bar. Empty string returns results for the whole country.
    :param offers_per_page: str, number of offers per page (as string)
    :param limit: int, if non-0 max number of offers
    :param filters: the following dict contains every possible filter with examples of its values, but can be empty:

    ::

        filters = {
            'distanceRadius: 0,  # distance from region
            'priceMin': 0,  # minimal price
            'priceMax': 0,  # maximal price
            'pricePerMeterMin': 0  # maximal price per square meter, only used for apartments for sale
            'pricePerMeterMax': 0  # minimal price per square meter, only used for apartments for sale
            'market':  'PRIMARY' # enum (str): PRIMARY, SECONDARY, ALL
            'buildingMaterial': ['BRICK']  # BRICK, WOOD, BREEZEBLOCK, HYDROTON, CONCRETE_PLATE, CONCRETE,
            SILIKAT, CELLULAR_CONCRETE, OTHER, REINFORCED_CONCRETE, only used for apartments for sale
            'areaMin': 0,  # minimal surface
            'areaMax: 0,  # maximal surface
            roomsNumber': [ONE, TWO, THREE]',  # number of rooms, enum: from "ONE" to "TEN", or "MORE"
            #'[private_business]': 'private',  # poster type, enum: private, business
            'hasOpenDay': 0,  # whether or not the poster organises an open day
            'isExclusiveOffer': 0,  # whether or not the offer is otodom exclusive
            #'[filter_enum_rent_to_students][]': 0,  # whether or not the offer is aimed for students, only used for
                apartments for rent
            'floors': ['CELLAR'],  #  : CELLAR, CELLAR,GROUND,FIRST,SECOND,THIRD to TENTH, ABOVE_TENTH, GARRET
                garret
            'floorsNumberMin': 1,  # minimal number of floors in the building
            'floorsNumberMax': 1,  # maximal number of floors in the building
            'buildingType': 'BLOCK' # enum (str) BLOCK,TENEMENT,HOUSE,INFILL,RIBBON,APARTMENT,LOFT
            #'[filter_enum_heating][]': 'urban',  # enum: urban, gas, tiled_stove, electrical, boiler_room, other
            'buildYearMin': 1980,  # minimal year the building was built in
            'buildYearMax': 2016,  # maximal year the building was built in
            'extras': ['BALCONY', 'BASEMENT'], # AIR_CONDITIONING, BALCONY, BASEMENT, GARAGE, GARDEN, LIFT, NON_SMOKERS_ONLY, SEPARATE_KITCHEN, TERRACE, TWO_STOREY, USABLE_ROOM]
            #'[filter_enum_media_types][]': ['internet', 'phone'],  # enum: internet, cable-television, phone
            #'[free_from]': 'from_now',  # when will it be possible to move in, enum: from_now, 30, 90
            'daysSinceCreated': 3,  # when was the offer posted on otodom in days, enum: 1, 3, 7, 14
            'id': 48326376,  # otodom offer ID, found at the very bottom of each offer
            'description': 'wygodne',  # the resulting offers' descriptions must contain this string
            'hasPhotos': false,  # bool whether or not the offer contains photos
            'hasMovie': false,  # bool whether or not the offer contains video
            'hasWalkaround'': false  # bool whether or not the offer contains a walkaround 3D view
            'city':  # lowercase, no diacritics, '-' instead of spaces, _city_id at the end
            'voivodeship':  # lowercase, no diacritics, '-' instead of spaces
            'district_id': from otodom API
            'street_id': from otodom API
        }

    :rtype: list of dict(string, string)
    :return: Each of the dictionaries contains the following fields:

    ::

        'detail_url' - a link to the offer
        'offer_id' - the internal otodom's offer ID, not to be mistaken with the '[id]' field from the input_dict
        'poster' - a piece of information about the poster. Could either be a name of the agency or "Oferta prywatna"
    """
    parsed_content = []
    region_data = get_region_from_autosuggest(region)
    real_num_of_offers = get_number_of_offers(
        main_category, detail_category, region_data, **filters
    )
    max_offers = min(12000, real_num_of_offers)
    limit = min(max_offers, limit) if limit else max_offers
    offers = 0
    page = 1
    offers_parsed = int(offers_per_page)

    while offers == 0 or offers < limit and offers_parsed >= int(offers_per_page):
        url = get_url(
            main_category,
            detail_category,
            region_data,
            offers_per_page,
            page,
            **filters
        )
        content = get_response_for_url(url).content
        if not was_category_search_successful(content):
            log.warning("Search for category wasn't successful", url)
            return []
        parsed_page = parse_category_content(content)
        offers_parsed = len(parsed_page)
        parsed_content.extend(parsed_page)
        offers += offers_parsed
        page += 1
    return parsed_content
