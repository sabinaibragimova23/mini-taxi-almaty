# MiniTaxi · Almaty

Student project "Mini Taxi Service" (Task 9): a website + backend built on our 5 tables
PASSENGERS, DRIVERS, CARS, RIDES, PAYMENTS.

## Run (2 commands)

```bash
pip install flask
python app.py
```

Open in the browser: http://127.0.0.1:5000

The `taxi.db` database (SQLite) is created automatically from `schema.sql` and filled with demo data
(8 passengers, 6 drivers, 7 cars, ~64 rides over 2 months).
To reset: log in as admin and press "Reset demo data" at the bottom, or delete `taxi.db`.

## Roles and login

On the login screen you pick a role. The server checks the role on every request: a wrong
role or someone else's ride gets a 403.

| Role | Login | Screens |
|---|---|---|
| Passenger | phone number, or "Create an account" | book a taxi on the map, current ride (driver, car, plate), cancel, trip history, pay again if the card failed |
| Driver | phone number | own profile and cars, the assigned ride with the passenger's phone, complete with cash or card, own earnings by month |
| Admin | password `admin123` (set `ADMIN_PASSWORD` to change it) | all rides, the 5 tables, reports, access table for Section 9 |

The login screen has buttons for a few demo accounts.

To show it in the presentation, log in as a passenger in one tab and book a ride. Then log in as
the assigned driver in another tab and complete it. Each tab keeps its own login, and the
passenger's tab picks up the change within about 5 seconds.

Passengers and drivers log in with a phone number only, since the schema has no password field.
Adding SMS codes or a password hash column would fix that.

## Files

- `app.py`: backend (Flask, REST API, fare, demo data)
- `schema.sql`: tables, PK, FK, CHECK constraints
- `queries.sql`: SQL queries for the presentation (Section 8)
- `static/`: frontend: `index.html`, `style.css`, `app.js`

## API

| Method | Path | Who | Description |
|---|---|---|---|
| GET | /api/places, POST /api/quote | everyone | Almaty places, route price |
| POST | /api/login, /api/signup | everyone | log in / passenger sign-up → token |
| GET | /api/me | any role | current user |
| GET | /api/my/rides | passenger | own rides |
| POST | /api/rides | passenger | book `{pickup, dropoff}` |
| POST | /api/rides/:id/cancel | passenger (own), admin | cancel an active ride |
| GET | /api/driver/rides, /api/driver/earnings | driver | own rides, own earnings |
| POST | /api/rides/:id/complete | driver (own) | complete + payment `{method}` in one transaction |
| POST | /api/rides/:id/pay | passenger / driver (own) | pay again by card / record cash |
| GET/POST | /api/passengers, /api/drivers, /api/cars | admin | list / add |
| GET | /api/rides, /api/payments, /api/stats | admin | all rides, payments, numbers |
| GET | /api/reports/driver-earnings?month=YYYY-MM | admin | earnings report |

## Fare

500 ₸ pickup + 140 ₸/km (distance × 1.35 for roads), minimum 800 ₸.
Medeu / Shymbulak: +600 ₸. Night (23:00–06:00): ×1.2.

## Business rules

- A driver has only one active ride at a time (status = requested).
- A passenger has only one active ride at a time.
- If all drivers are busy, the ride is not created (error 409).
- Only an active ride can be completed or cancelled.
- You can't create a car for a driver that doesn't exist (FK), or a ride for a passenger that doesn't exist.
- Phone: +7 7XX XXX XX XX, plate: 123 ABC 02.
