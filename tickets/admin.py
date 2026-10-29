from django.contrib import admin

from .models import Event, Reservation, ReservationSeat, Seat, Venue

admin.site.register(Venue)
admin.site.register(Event)
admin.site.register(Seat)
admin.site.register(Reservation)
admin.site.register(ReservationSeat)
