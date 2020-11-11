import json
import ast
from amadeus import Client, ResponseError, Location
from django.shortcuts import render
from django.contrib import messages
from .flight import Flight
from .metrics import Metrics
from django.http import HttpResponse

amadeus = Client()


def flight_offers(request):
    origin = request.POST.get('Origin')
    destination = request.POST.get('Destination')
    departure_date = request.POST.get('Departuredate')
    return_date = request.POST.get('Returndate')

    kwargs = {'originLocationCode': origin,
              'destinationLocationCode': destination,
              'departureDate': departure_date,
              'adults': 1
              }

    kwargs_metrics = {'originIataCode': origin,
                      'destinationIataCode': destination,
                      'departureDate': departure_date
                      }
    tripPurpose = ''
    if return_date:
        kwargs['returnDate'] = return_date
        kwargs_trip_purpose = {'originLocationCode': origin,
                               'destinationLocationCode': destination,
                               'departureDate': departure_date,
                               'returnDate': return_date
                               }
        tripPurpose = get_trip_purpose(request, **kwargs_trip_purpose)
    else:
        kwargs_metrics['oneWay'] = 'true'

    if origin and destination and departure_date:
        try:
            search_flights = amadeus.shopping.flight_offers_search.get(**kwargs)
            metrics = get_flight_price_metrics(request, **kwargs_metrics)

        except ResponseError as error:
            messages.add_message(request, messages.ERROR, error)
            return render(request, 'flight_price/home.html', {})
        search_flights_returned = []
        for flight in search_flights.data:
            offer = Flight(flight).construct_flights()
            search_flights_returned.append(offer)
            response = zip(search_flights_returned, search_flights.data)
        cheapest_flight = get_cheapest_flight_price(search_flights_returned)
        is_good_deal = evaluate_cheapest_flight(cheapest_flight, metrics.get('first'), metrics.get('third'))
        is_cheapest_flight_out_of_range(cheapest_flight, metrics)

        return render(request, 'flight_price/results.html', {'response': response,
                                                             'origin': origin,
                                                             'destination': destination,
                                                             'departureDate': departure_date,
                                                             'returnDate': return_date,
                                                             'tripPurpose': tripPurpose,
                                                             'metrics': metrics,
                                                             'cheapest_flight': cheapest_flight,
                                                             'is_good_deal': is_good_deal
                                                            })
    return render(request, 'flight_price/home.html', {})


def origin_airport_search(request):
    if request.is_ajax():
        try:
            data = amadeus.reference_data.locations.get(keyword=request.GET.get('term', None),
                                                        subType=Location.ANY).data
        except ResponseError as error:
            messages.add_message(request, messages.ERROR, error)
    return HttpResponse(get_city_airport_list(data), 'application/json')


def destination_airport_search(request):
    if request.is_ajax():
        try:
            data = amadeus.reference_data.locations.get(keyword=request.GET.get('term', None),
                                                        subType=Location.ANY).data
        except ResponseError as error:
            messages.add_message(request, messages.ERROR, error)
    return HttpResponse(get_city_airport_list(data), 'application/json')


def get_city_airport_list(data):
    result = []
    for i, val in enumerate(data):
        result.append(data[i]['iataCode'] + ', ' + data[i]['name'])
    result = list(dict.fromkeys(result))

    return json.dumps(result)


def get_flight_price_metrics(request, **kwargs_metrics):
    try:
        kwargs_metrics['currencyCode'] = 'USD'
        metrics = amadeus.analytics.itinerary_price_metrics.get(**kwargs_metrics)
        metrics_returned = Metrics(metrics.data).construct_metrics()
    except ResponseError as error:
        messages.add_message(request, messages.ERROR, error)
    return metrics_returned


def get_trip_purpose(request, **kwargs_trip_purpose):
    try:
        trip_purpose = amadeus.travel.predictions.trip_purpose.get(**kwargs_trip_purpose).data
    except ResponseError as error:
        messages.add_message(request, messages.ERROR, error)
        return render(request, 'flight_price/home.html', {})
    return trip_purpose['result']


def get_cheapest_flight_price(flight_offers):
    return flight_offers[0]['price']

def evaluate_cheapest_flight(cheapest_flight_price, first_price, third_price):
    cheapest_flight_price_to_number = float(cheapest_flight_price)
    first_price_to_number = float(first_price)
    third_price_to_number = float(third_price)
    if cheapest_flight_price_to_number < first_price_to_number:
        return 'A GOOD DEAL'
    elif cheapest_flight_price_to_number > third_price_to_number:
        return 'HIGH'
    else:
        return 'TYPICAL'

def is_cheapest_flight_out_of_range(cheapest_flight_price, metrics):
    min_price = float(metrics['min'])
    max_price = float(metrics['max'])
    cheapest_flight_price_to_number = float(cheapest_flight_price)
    if cheapest_flight_price_to_number < min_price:
        metrics['min'] = cheapest_flight_price
    elif cheapest_flight_price_to_number > max_price:
        metrics['max'] = cheapest_flight_price
