# Hotel booking demand (Resort Hotel)

Discovery case from v0.3: the first study a junior runs. A **binary** scoring study on real bookings of a resort hotel, with a clear timeline: the prediction is made when a booking is entered, the outcome (a cancellation) comes later, and several columns of the file are recorded after the booking. Those columns are the leakage traps of the case.

## Scenario

A resort hotel loses revenue when bookings are cancelled. Its reservations team has limited staff: it can contact only some new bookings, to reconfirm them or to ask for a deposit. **When a booking is entered** in the hotel's property management system (PMS), a score ranks it by risk of cancellation, and the team handles the top share.

- **Observation unit**: one booking of the Resort Hotel (H1).
- **Target**: `is_canceled`, 1 when the booking was cancelled, 0 otherwise (`positive_label: '1'`). It is strictly after the prediction moment.
- **Prediction moment**: the day the booking is entered in the PMS, the start of `lead_time`.
- **Action**: contact, or ask a deposit from, the top share of new bookings by score. `scenario_defaults.capacity_share` is **10 %** (`scenario_assumption`), as in the other teaching cases: the team can handle one new booking in ten. The agent asks the capacity as a share and shows 5, 10 and 20 %; keeping the default is listed as "capacity assumed for the exercise". The data record no contact and no deposit request made because of a score, so they say nothing about whether either prevents a cancellation (fact `causal_effect`).
- **Interpretability**: `constraints.interpretability` is **`preferred`** (`scenario_assumption`, v0.3): the team contacts a customer or asks a deposit because of the score and should be able to say which booking details raised it; no rule of the hotel is known that requires a readable model. The engine's shortlist of model families then lists the Explainable Boosting Machine before gradient boosting and excludes neither (CASE-CONTRACT, "Constraints").

## What is known when the booking is entered

Every statement below is in `case.yaml`, with its source. The variable descriptions come from the tidytuesday data dictionary (see Sources); the timing statements are `scenario_assumption` unless the definition itself places the column after the booking.

| Availability | Columns | Why |
|---|---|---|
| Available | `lead_time`, `arrival_date_year`, `arrival_date_month`, `arrival_date_week_number`, `arrival_date_day_of_month`, `stays_in_weekend_nights`, `stays_in_week_nights`, `adults`, `children`, `babies`, `meal`, `reserved_room_type`, `market_segment`, `distribution_channel`, `agent`, `company`, `customer_type`, `is_repeated_guest`, `previous_cancellations`, `previous_bookings_not_canceled` | What the customer asks, how the booking is sold, and the guest's history before this booking. See the snapshot limit below. |
| **Not available** (the outcome) | `reservation_status`, `reservation_status_date` | The last status (Canceled, Check-Out, No-Show) and its date *are* the outcome. Dictionary definitions. |
| **Not available** (after the booking) | `booking_changes` | Counts the amendments "from the moment the booking was entered on the PMS until the moment of check-in or cancellation" (dictionary). |
| | `days_in_waiting_list` | Days "in the waiting list before it was confirmed to the customer" (dictionary): the wait starts when the booking is entered, so the count is not known then. It would be known if the prediction moment were that confirmation. (`case.yaml` paraphrases "confirmed" as "accepted": a case file never contains that word.) |
| | `assigned_room_type` | The room the hotel assigned; it can differ from the reserved one because of overbooking or a customer request (dictionary). When it is assigned is **not documented**: the case assumes close to arrival or at check-in (the preparer's assumption about hotel practice). |
| **Uncertain** | `country` | The article warns that hotels often do not know the correct nationality until check-in. |
| | `deposit_type` | When the deposit was made or required is not documented; it is also the action of this scenario, so it records the hotel's past deposit policy. |
| | `adr` | Average daily rate, "the sum of all lodging transactions divided by the total number of staying nights": quoted at booking or charged later is not documented. One row has a negative rate (`range` min 0). |
| | `required_car_parking_spaces`, `total_of_special_requests` | Uncertain timing: the dictionary does not say when requests are made. |

**The snapshot limit.** The article states that "the data point time for each observation was defined as the day prior to each booking's arrival": values were read from the bookings change log at that date, not at booking. So even the "available" columns hold the value of the day before arrival (for a cancelled booking, presumably the last value before the cancellation); an amendment between the booking and that day is included. The article adds that customers often change the number of persons, the duration, or the room type, and that the nationality is often known only at check-in. A model fitted on this file can look better than one fed with the values at booking (fact `snapshot_limit`).

## Structure

- **Temporal final test by arrival date.** The file is sorted by arrival date (built from `arrival_date_year`, `arrival_date_month`, `arrival_date_day_of_month`), and the case declares `order: {by: line, direction: ascending}` (`observed`, checked by `--verify`), as Bank Marketing full does. `init` seals the latest fifth of the arrivals: **8,011 rows**, from the arrivals of 13 April 2017 to 31 August 2017 (20 % is 8,012: one row, a copy of a duplicate group divided by the cut, moves to the development side with its group); the 32,049 earlier arrivals are the development rows. The final test is in the future by arrival date, not by booking date: with lead times up to two years, some sealed bookings were entered before some development bookings arrived.
- **Duplicates.** 6,092 rows repeat an earlier row on every column (2,325 groups, 8,417 rows), plausibly rooms of one group booking, but nothing says so. The case declares `duplicates: {policy: group}`: each group stays on one side of the final test, the split and the folds.
- No customer identifier (removed by the authors); `previous_*` show that a customer can have several bookings.
- `NULL` is a category, not a missing value: for `agent` and `company` it means "not applicable" (the article); for `country` (464 rows) its meaning is not documented. `meal` codes `Undefined` and `SC` both mean "no meal package" (dictionary). `distribution_channel = Undefined` (1 row) is undocumented.

## Data and licence

`data/hotel-resort.csv`: 40,060 bookings, 31 columns, comma-separated, LF line ends, 5.2 MB. Source: Antonio, N., de Almeida, A., and Nunes, L. (2019). Hotel booking demand datasets. *Data in Brief* 22, 41–49. doi:[10.1016/j.dib.2018.11.126](https://doi.org/10.1016/j.dib.2018.11.126). Licence **CC BY 4.0**, the licence of the open-access article the data are supplied with ("Data is supplied with the paper", Specifications table); a separate wording for the data files was not read. See also [THIRD_PARTY_NOTICES.md](../../THIRD_PARTY_NOTICES.md).

## Provenance and verification

The authors' files could not be reached from the preparation environment. On 2026-10-20 the combined file of the tidytuesday project was downloaded into an empty folder and read with pandas as text only: `https://raw.githubusercontent.com/rfordatascience/tidytuesday/master/data/2020/2020-02-11/hotels.csv`, sha256 `7c2ae42a7353905ea136e5c2287f17c92c5435826598bfbb8491c6f0c7b1fc06`. It holds both hotels, adds a `hotel` column, and uses snake-case column names (`janitor::clean_names`, per its cleaning script).

| Check | Article (abstract) | Mirror file |
|---|---|---|
| Rows, both hotels | 119,390 (40,060 + 79,330) | 119,390 |
| Resort Hotel (H1) | 40,060 | 40,060 |
| City Hotel (H2) | 79,330 | 79,330 |
| Variables | 31 | 31, plus `hotel` |
| Arrival dates | 1 July 2015 to 31 August 2017 | 2015-07-01 to 2017-08-31 (Resort) |

Cancellations counted in the mirror file (the article publishes none): Resort 11,122 of 40,060 (27.8 %), City 33,102 of 79,330 (41.7 %), both 44,224 of 119,390 (37.0 %). In the Resort rows, `is_canceled` is 1 exactly when `reservation_status` is `Canceled` (10,831) or `No-Show` (291). These counts were made on every row, the future final test included; the case records that as prior exposure.

`build_case.py --derive hotels.csv` checks the mirror's sha256 and these counts, then writes `data/hotel-resort.csv`: the Resort rows, without the constant `hotel` column, sorted by arrival date (stable: the mirror's order is kept within a date), every cell copied as text. Its sha256 is `cad1f2500c152b5733f1dc26023ae2975f76c186da18c057ab85732f18d00782`. `--verify` re-checks rows, columns, `is_canceled` counts, the arrival range and the order. The file was not compared byte for byte with the authors' files. **To do on a machine that reaches them:** compare H1 with the Resort rows of the mirror.

## Sources

- The article, read through PubMed Central (PMC6297060, PMID 30581903): the abstract (unit, counts, period), the Specifications table (data point time, location), sections 1 and 2 (change-log snapshot, `NULL` categories, the word of caution on changed attributes and nationality). Its Table 1, the variable descriptions, was not in the retrieved text.
- The tidytuesday data dictionary, `https://raw.githubusercontent.com/rfordatascience/tidytuesday/master/data/2020/2020-02-11/readme.md`, which credits the article: every variable description (cited per variable in `case.yaml`).
- The preparer's assumption: when `assigned_room_type` is set (not documented).

## Files

- `data/hotel-resort.csv`: the data (derived, see above).
- `build_case.py`: derives the data (`--derive`), generates `case.yaml` (`--check` compares it, `--verify` re-runs the integrity checks, `--out DIR` writes a copy for tests). `mlkit.study.migrate` does not apply: there is no companion `project.json`.
- `case.yaml`: the [`hypotrail.case/1`](../../docs/specs/CASE-CONTRACT.md) adapter, with the variable groups and French labels. Edit `build_case.py`, never the YAML.

## Running the study

```sh
uv sync --project framework --group dev
uv run --project framework hypotrail init --case use-cases/hotel-booking/case.yaml --study ~/studies/hotel
cd ~/studies/hotel && claude
```

Create the study outside the repository.
